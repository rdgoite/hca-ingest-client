import re
from abc import abstractmethod

from ingest.importer.conversion import data_converter
from ingest.importer.conversion.column_specification import ColumnSpecification, ConversionType
from ingest.importer.conversion.data_converter import Converter, ListConverter
from ingest.importer.conversion.exceptions import UnknownMainCategory
from ingest.importer.conversion.metadata_entity import MetadataEntity
from ingest.importer.conversion.utils import split_field_chain
from ingest.importer.data_node import DataNode

_LIST_CONVERTER = ListConverter()


class CellConversion(object):

    def __init__(self, field, converter: Converter):
        self.field = field
        self.applied_field = self._process_applied_field(field)
        self.converter = converter

    @staticmethod
    def _process_applied_field(field):
        pattern = '(\w*\.){0,1}(?P<insert_field>.*)'
        match = re.match(pattern, field)
        return match.group('insert_field')

    @abstractmethod
    def apply(self, metadata: MetadataEntity, cell_data): ...


class DirectCellConversion(CellConversion):

    def apply(self, metadata: MetadataEntity, cell_data):
        if cell_data is not None:
            content = self.converter.convert(cell_data)
            metadata.define_content(self.applied_field, content)


class ListElementCellConversion(CellConversion):

    def __init__(self, field: str, converter: Converter):
        list_converter = ListConverter(base_converter=converter)
        super(ListElementCellConversion, self).__init__(field, list_converter)

    def apply(self, metadata: MetadataEntity, cell_data):
        if cell_data is not None:
            parent_path, target_field = split_field_chain(self.applied_field)
            data_list = self.converter.convert(cell_data)
            parent = self._prepare_array(metadata, parent_path, len(data_list))
            for index, data in enumerate(data_list):
                target_object = parent[index]
                target_object[target_field] = data

    @staticmethod
    def _prepare_array(metadata, path, child_count):
        parent = metadata.get_content(path)
        if parent is None:
            parent = [{} for _ in range(0, child_count)]
            metadata.define_content(path, parent)
        # TODO what if the next batch is of fields is larger than the first batch?
        # e.g. [ {age: 1, name: x}, {age: 2, name: y}, {name: z} ] <- 2 ages, 3 names
        return parent


class IdentityCellConversion(CellConversion):

    def apply(self, metadata: MetadataEntity, cell_data):
        value = self.converter.convert(cell_data)
        metadata.object_id = value
        metadata.define_content(self.applied_field, value)


class LinkedIdentityCellConversion(CellConversion):

    def __init__(self, field, main_category):
        super(LinkedIdentityCellConversion, self).__init__(field, _LIST_CONVERTER)
        self.main_category = main_category

    def apply(self, metadata: MetadataEntity, cell_data):
        if self.main_category is None:
            raise UnknownMainCategory()
        if cell_data is not None:
            links = self.converter.convert(cell_data)
            metadata.add_links(self.main_category, links)


class ExternalReferenceCellConversion(CellConversion):

    def __init__(self, field, main_category):
        super(ExternalReferenceCellConversion, self).__init__(field, _LIST_CONVERTER)
        self.main_category = main_category

    def apply(self, metadata: MetadataEntity, cell_data):
        link_ids = self.converter.convert(cell_data)
        metadata.add_external_links(self.main_category, link_ids)


class LinkingDetailCellConversion(CellConversion):

    def apply(self, metadata: MetadataEntity, cell_data):
        value = self.converter.convert(cell_data)
        metadata.define_linking_detail(self.applied_field, value)


class DoNothing(CellConversion):

    def __init__(self):
        super(DoNothing, self).__init__('', data_converter.DEFAULT)

    def apply(self, metadata: MetadataEntity, cell_data):
        pass


DO_NOTHING = DoNothing()


def determine_strategy(column_spec: ColumnSpecification):
    strategy = DO_NOTHING
    if column_spec is not None:
        field_name = column_spec.field_name
        converter = column_spec.determine_converter()
        conversion_type = column_spec.get_conversion_type()
        if ConversionType.MEMBER_FIELD == conversion_type:
            strategy = DirectCellConversion(field_name, converter)
        elif ConversionType.FIELD_OF_LIST_ELEMENT == conversion_type:
            strategy = ListElementCellConversion(field_name, converter)
        elif ConversionType.LINKING_DETAIL == conversion_type:
            strategy = LinkingDetailCellConversion(field_name, converter)
        elif ConversionType.IDENTITY == conversion_type:
            strategy = IdentityCellConversion(field_name, converter)
        elif ConversionType.LINKED_IDENTITY == conversion_type:
            strategy = LinkedIdentityCellConversion(field_name, column_spec.main_category)
        elif ConversionType.EXTERNAL_REFERENCE == conversion_type:
            strategy = ExternalReferenceCellConversion(field_name, column_spec.main_category)
    return strategy
