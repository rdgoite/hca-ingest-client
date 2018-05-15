from unittest import TestCase

from mock import MagicMock, patch
from openpyxl import Workbook

from ingest.importer.conversion import template_manager
from ingest.importer.conversion.data_converter import (
    Converter, ListConverter, BooleanConverter, DataType
)
from ingest.importer.conversion.template_manager import TemplateManager
from ingest.importer.data_node import DataNode
from ingest.importer.importer import WorksheetImporter, WorkbookImporter
from ingest.importer.spreadsheet.ingest_workbook import IngestWorkbook
from ingest.template.schematemplate import SchemaTemplate


def _create_single_row_worksheet(worksheet_data:dict):
    workbook = Workbook()
    worksheet = workbook.create_sheet()

    for column, data in worksheet_data.items():
        key, value = data
        worksheet[f'{column}1'] = key
        worksheet[f'{column}4'] = value

    return worksheet


class WorkbookImporterTest(TestCase):

    @patch('ingest.importer.importer.WorksheetImporter')
    @patch.object(template_manager, 'build')
    def test_do_import(self, template_manager_build, worksheet_importer_constructor):
        # given: set up template manager
        mock_template_manager = MagicMock()
        template_manager_build.return_value = mock_template_manager

        # and: set up worksheet importer
        worksheet_importer = WorksheetImporter()
        expected_json_list = self._fake_worksheet_import(worksheet_importer, mock_template_manager)

        # and: set up workbook
        workbook = Workbook()
        ingest_workbook = IngestWorkbook(workbook)
        schema_list = self._mock_get_schemas(ingest_workbook)
        self._mock_importable_worksheets(ingest_workbook, workbook)

        # and: mock WorksheetImporter constructor
        worksheet_importer_constructor.return_value = worksheet_importer
        workbook_importer = WorkbookImporter()

        # when:
        actual_json_list = workbook_importer.do_import(ingest_workbook)

        # then:
        template_manager_build.assert_called_with(schema_list)

        # and:
        self.assertEqual(3, len(actual_json_list))
        for expected_json in expected_json_list:
            self.assertTrue(expected_json in actual_json_list, f'{expected_json} not in list')

    def _mock_get_schemas(self, ingest_workbook):
        schema_base_url = 'https://schema.humancellatlas.org'
        schema_list = [
            f'{schema_base_url}/type/project',
            f'{schema_base_url}/type/biomaterial'
        ]
        ingest_workbook.get_schemas = MagicMock(return_value=schema_list)
        return schema_list

    def _mock_importable_worksheets(self, ingest_workbook, workbook):
        project_worksheet = workbook.create_sheet('Project')
        cell_suspension_worksheet = workbook.create_sheet('Cell Suspension')
        ingest_workbook.importable_worksheets = MagicMock(return_value=[
            project_worksheet, cell_suspension_worksheet
        ])

    def _fake_worksheet_import(self, worksheet_importer:WorksheetImporter, mock_template_manager):
        projects = [
            {'short_name': 'project 1', 'description': 'first project'},
            {'short_name': 'project 2', 'description': 'second project'}
        ]

        cell_suspensions = [
            {'biomaterial_id': 'cell_suspension_101', 'biomaterial_name': 'cell suspension'}
        ]

        worksheet_iterator = iter([projects, cell_suspensions])
        worksheet_importer.do_import = (
            lambda __, tm: worksheet_iterator.__next__() if tm is mock_template_manager else []
        )
        return projects + cell_suspensions


class WorksheetImporterTest(TestCase):

    # TODO refactor this
    def test_do_import(self):
        # given:
        worksheet_importer = WorksheetImporter()

        # and:
        boolean_converter = BooleanConverter()
        converter_mapping = {
            'project.project_core.project_shortname': Converter(),
            'project.miscellaneous': ListConverter(),
            'project.numbers': ListConverter(data_type=DataType.INTEGER),
            'project.is_active': boolean_converter,
            'project.is_submitted': boolean_converter
        }

        # and:
        mock_template_manager = MagicMock(name='template_manager')
        mock_template_manager.create_template_node = lambda __: DataNode()
        mock_template_manager.get_converter = lambda key: converter_mapping.get(key, Converter())
        mock_template_manager.is_ontology_subfield = lambda __: False

        # and:
        worksheet = self._create_test_worksheet()

        # when:
        json_list = worksheet_importer.do_import(worksheet, mock_template_manager, 'project')

        # then:
        self.assertEqual(2, len(json_list))
        json = json_list[0]

        # and:
        self.assertTrue(2, len(json_list))
        self.assertEqual('Tissue stability 2', json_list[1]['project_core']['project_shortname'])

        project_core = json['project_core']
        self.assertEqual('Tissue stability', project_core['project_shortname'])
        self.assertEqual('Ischaemic sensitivity of human tissue by single cell RNA seq.',
                         project_core['project_title'])

        # and:
        self.assertEqual(2, len(json['miscellaneous']))
        self.assertEqual(['extra', 'details'], json['miscellaneous'])

        # and:
        self.assertEqual(7, json['contributor_count'])

        # and:
        self.assertEqual('Juan Dela Cruz||John Doe', json['contributors'])

        # and:
        self.assertEqual([1, 2, 3], json['numbers'])

        # and:
        self.assertEqual(True, json['is_active'])
        self.assertEqual(False, json['is_submitted'])

    def _create_test_worksheet(self):
        workbook = Workbook()
        worksheet = workbook.create_sheet('Project')
        worksheet['A1'] = 'project.project_core.project_shortname'
        worksheet['A4'] = 'Tissue stability'
        worksheet['A5'] = 'Tissue stability 2'
        worksheet['B1'] = 'project.project_core.project_title'
        worksheet['B4'] = 'Ischaemic sensitivity of human tissue by single cell RNA seq.'
        worksheet['C1'] = 'project.miscellaneous'
        worksheet['C4'] = 'extra||details'
        worksheet['D1'] = 'project.contributor_count'
        worksheet['D4'] = 7
        worksheet['E1'] = 'project.contributors'
        worksheet['E4'] = 'Juan Dela Cruz||John Doe'
        worksheet['F1'] = 'project.numbers'
        worksheet['F4'] = '1||2||3'
        worksheet['G1'] = 'project.is_active'
        worksheet['G4'] = 'Yes'
        worksheet['H1'] = 'project.is_submitted'
        worksheet['H4'] = 'No'

        return worksheet

    def test_do_import_with_ontology_fields(self):
        # given:
        template_manager = MagicMock(name='template_manager')
        template_manager.create_template_node = lambda __: DataNode()
        template_manager.get_converter = MagicMock(return_value=Converter())

        # and:
        ontology_fields_mapping = {
            'project.genus_species.ontology': True,
            'project.genus_species.text': True,
        }
        template_manager.is_ontology_subfield = (
            lambda field_name: ontology_fields_mapping.get(field_name)
        )

        # and:
        worksheet = _create_single_row_worksheet({
            'A': ('project.genus_species.ontology', 'UO:000008'),
            'B': ('project.genus_species.text', 'meter')
        })

        # and:
        worksheet_importer = WorksheetImporter()

        # when:
        json_list = worksheet_importer.do_import(worksheet, template_manager, 'project')

        # then:
        self.assertEqual(1, len(json_list))
        json = json_list[0]

        # and:
        self.assertTrue(type(json['genus_species']) is list)
        self.assertEqual(1, len(json['genus_species']))
        self.assertEqual({'ontology': 'UO:000008', 'text': 'meter'}, json['genus_species'][0])

    @patch('ingest.importer.importer.OntologyTracker')
    def test_do_import_builds_from_template(self, ontology_tracker_constructor):
        # given:
        mock_template_manager = MagicMock(name='template_manager')
        mock_template_manager.get_converter = MagicMock(return_value=Converter())

        # and:
        node_template = DataNode()
        node_template['describedBy'] = 'https://schemas.sample.com/test'
        node_template['extra_field'] = 'an extra field'
        node_template['version'] = '0.0.1'
        mock_template_manager.create_template_node = lambda __: node_template

        # and:
        ontology_tracker_constructor.return_value = MagicMock(name='ontology_tracker')

        # and:
        importer = WorksheetImporter()

        # and:
        worksheet = _create_single_row_worksheet({
            'A': ('project.short_name', 'Project'),
            'B': ('project.description', 'This is a project')
        })

        # when:
        json_list = importer.do_import(worksheet, mock_template_manager, 'project')

        # then:
        self.assertEqual(1, len(json_list))
        json = json_list[0]

        # and:
        self.assertEqual('https://schemas.sample.com/test', json.get('describedBy'))
        self.assertEqual('an extra field', json.get('extra_field'))
        self.assertEqual('0.0.1', json.get('version'))
