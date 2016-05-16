from lxml import etree
from lxml.etree import SubElement
from oaipmh import common

class MetadataRegistry(object):
    """A registry that contains readers and writers of metadata.

    a reader is a function that takes a chunk of (parsed) XML and
    returns a metadata object.

    a writer is a function that takes a takes a metadata object and
    produces a chunk of XML in the right format for this metadata.
    """
    def __init__(self):
        self._readers = {}
        self._writers = {}
        
    def registerReader(self, metadata_prefix, reader):
        self._readers[metadata_prefix] = reader

    def registerWriter(self, metadata_prefix, writer):
        self._writers[metadata_prefix] = writer

    def hasReader(self, metadata_prefix):
        return metadata_prefix in self._readers
    
    def hasWriter(self, metadata_prefix):
        return metadata_prefix in self._writers
    
    def readMetadata(self, metadata_prefix, element):
        """Turn XML into metadata object.

        element - element to read in

        returns - metadata object
        """
        return self._readers[metadata_prefix](element)

    def writeMetadata(self, metadata_prefix, element, metadata):
        """Write metadata as XML.
        
        element - ElementTree element to write under
        metadata - metadata object to write
        """
        self._writers[metadata_prefix](element, metadata)

global_metadata_registry = MetadataRegistry()

class Error(Exception):
    pass

class MetadataReader(object):
    """A default implementation of a reader based on fields.
    """
    def __init__(self, fields, namespaces=None):
        self._fields = fields
        self._namespaces = namespaces or {}

    def __call__(self, element):
        map = {}
        # create XPathEvaluator for this element
        xpath_evaluator = etree.XPathEvaluator(element, 
                                               namespaces=self._namespaces)
        
        map['element'] = element
        e = xpath_evaluator.evaluate
        # now extra field info according to xpath expr
        for field_name, (field_type, expr) in list(self._fields.items()):
            if field_type == 'bytes':
                value = str(e(expr))
            elif field_type == 'bytesList':
                value = [str(item) for item in e(expr)]
            elif field_type == 'text':
                # make sure we get back unicode strings instead
                # of lxml.etree._ElementUnicodeResult objects.
                value = str(e(expr))
            elif field_type == 'textList':
                # make sure we get back unicode strings instead
                # of lxml.etree._ElementUnicodeResult objects.
                value = [str(v) for v in e(expr)]
            else:
                raise Error("Unknown field type: %s" % field_type)
            map[field_name] = value
        return common.Metadata(element, map)

oai_dc_reader = MetadataReader(
    fields={
    'title':       ('textList', 'oai_dc:dc/dc:title/text()'),
    'creator':     ('textList', 'oai_dc:dc/dc:creator/text()'),
    'subject':     ('textList', 'oai_dc:dc/dc:subject/text()'),
    'description': ('textList', 'oai_dc:dc/dc:description/text()'),
    'publisher':   ('textList', 'oai_dc:dc/dc:publisher/text()'),
    'contributor': ('textList', 'oai_dc:dc/dc:contributor/text()'),
    'date':        ('textList', 'oai_dc:dc/dc:date/text()'),
    'type':        ('textList', 'oai_dc:dc/dc:type/text()'),
    'format':      ('textList', 'oai_dc:dc/dc:format/text()'),
    'identifier':  ('textList', 'oai_dc:dc/dc:identifier/text()'),
    'source':      ('textList', 'oai_dc:dc/dc:source/text()'),
    'language':    ('textList', 'oai_dc:dc/dc:language/text()'),
    'relation':    ('textList', 'oai_dc:dc/dc:relation/text()'),
    'coverage':    ('textList', 'oai_dc:dc/dc:coverage/text()'),
    'rights':      ('textList', 'oai_dc:dc/dc:rights/text()')
    },
    namespaces={
    'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
    'dc' : 'http://purl.org/dc/elements/1.1/'}
    )


base_dc_reader = MetadataReader(
    fields={
    'title':       ('textList', 'base_dc:dc/dc:title/text()'),
    'creator':     ('textList', 'base_dc:dc/dc:creator/text()'),
    'subject':     ('textList', 'base_dc:dc/dc:subject/text()'),
    'description': ('textList', 'base_dc:dc/dc:description/text()'),
    'publisher':   ('textList', 'base_dc:dc/dc:publisher/text()'),
    'contributor': ('textList', 'base_dc:dc/dc:contributor/text()'),
    'date':        ('textList', 'base_dc:dc/dc:date/text()'),
    'type':        ('textList', 'base_dc:dc/dc:type/text()'),
    'format':      ('textList', 'base_dc:dc/dc:format/text()'),
    'identifier':  ('textList', 'base_dc:dc/dc:identifier/text()'),
    'source':      ('textList', 'base_dc:dc/dc:source/text()'),
    'language':    ('textList', 'base_dc:dc/dc:language/text()'),
    'relation':    ('textList', 'base_dc:dc/dc:relation/text()'),
    'coverage':    ('textList', 'base_dc:dc/dc:coverage/text()'),
    'rights':      ('textList', 'base_dc:dc/dc:rights/text()'),
    'autoclasscode':('textList', 'base_dc:dc/base_dc:autoclasscode/text()'),
    'classcode':('textList', 'base_dc:dc/base_dc:classcode/text()'),
    'collection':('textList', 'base_dc:dc/base_dc:collection/text()'),
    'collname':('textList', 'base_dc:dc/base_dc:collname/text()'),
    'continent':('textList', 'base_dc:dc/base_dc:continent/text()'),
    'country':('textList', 'base_dc:dc/base_dc:country/text()'),
    'lang':('textList', 'base_dc:dc/base_dc:lang/text()'),
    'link':('textList', 'base_dc:dc/base_dc:link/text()'),
    'oa':('textList', 'base_dc:dc/base_dc:oa/text()'),
    'rightsnorm':('textList', 'base_dc:dc/base_dc:rightsnorm/text()'),
    'typenorm':('textList', 'base_dc:dc/base_dc:typenorm/text()'),
    'year':('textList', 'base_dc:dc/base_dc:year/text()'),
    },
    namespaces={
    'base_dc': 'http://oai.base-search.net/base_dc/',
    'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
    'dc' : 'http://purl.org/dc/elements/1.1/'}
    )


    
