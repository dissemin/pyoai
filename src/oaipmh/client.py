# Copyright 2003, 2004, 2005 Infrae
# Released under the BSD license (see LICENSE.txt)
from __future__ import nested_scopes
import urllib2
import base64
from urllib import urlencode
from StringIO import StringIO
from types import SliceType
from lxml import etree
import time

from oaipmh import common, metadata, validation, error

WAIT_DEFAULT = 120 # two minutes
WAIT_MAX = 5

class Error(Exception):
    pass

class BaseClient(common.OAIPMH):

    def __init__(self, metadata_registry=None):
        self._metadata_registry = (
            metadata_registry or metadata.global_metadata_registry)
        self._ignore_bad_character_hack = 0
    
    def handleVerb(self, verb, kw):
        # validate kw first
        validation.validateArguments(verb, kw)
        # encode datetimes as datestamps
        from_ = kw.get('from_')
        if from_ is not None:
            # turn it into 'from', not 'from_' before doing actual request
            kw['from'] = common.datetime_to_datestamp(from_)
            del kw['from_']
        until = kw.get('until')
        if until is not None:
            kw['until'] = common.datetime_to_datestamp(until)
        # now call underlying implementation
        method_name = verb + '_impl'
        return getattr(self, method_name)(
            kw, self.makeRequestErrorHandling(verb=verb, **kw))    

    def getNamespaces(self):
        """Get OAI namespaces.
        """
        return {'oai': 'http://www.openarchives.org/OAI/2.0/'}

    def getMetadataRegistry(self):
        """Return the metadata registry in use.

        Do we want to allow the returning of the global registry?
        """
        return self._metadata_registry

    def ignoreBadCharacters(self, true_or_false): 	 
        """Set to ignore bad characters in UTF-8 input. 	 
        This is a hack to get around well-formedness errors of 	 
        input sources which *should* be in UTF-8 but for some reason 	 
        aren't completely. 	 
        """ 	 
        self._ignore_bad_character_hack = true_or_false 	 

    def parse(self, xml): 	 
        """Parse the XML to a lxml tree. 	 
        """
        # XXX this is only safe for UTF-8 encoded content, 	 
        # and we're basically hacking around non-wellformedness anyway,
        # but oh well
        if self._ignore_bad_character_hack: 	 
            xml = unicode(xml, 'UTF-8', 'replace') 	 
            # also get rid of character code 12 	 
            xml = xml.replace(chr(12), '?')
        else:
            xml = unicode(xml, 'UTF-8')
        return etree.XML(xml)

    def GetRecord_impl(self, args, tree):
        records, token = self.buildRecords(
            args['metadataPrefix'],
            self.getNamespaces(),
            self._metadata_registry,
            tree
            )
        assert token is None
        return records[0]

    # implementation of the various methods, delegated here by
    # handleVerb method
    
    def Identify_impl(self, args, tree):
        namespaces = self.getNamespaces()
        evaluator = etree.XPathEvaluator(tree, namespaces)
        identify_node = evaluator.evaluate(
            '/oai:OAI-PMH/oai:Identify')[0]
        identify_evaluator = etree.XPathEvaluator(identify_node, namespaces)
        e = identify_evaluator.evaluate

        repositoryName = e('string(oai:repositoryName/text())')
        baseURL = e('string(oai:baseURL/text())')
        protocolVersion = e('string(oai:protocolVersion/text())')
        adminEmails = e('oai:adminEmail/text()')
        earliestDatestamp = common.datestamp_to_datetime(
            e('string(oai:earliestDatestamp/text())'))
        deletedRecord = e('string(oai:deletedRecord/text())')
        granularity = e('string(oai:granularity/text())')
        compression = e('oai:compression/text()')
        # XXX description
        identify = common.Identify(
            repositoryName, baseURL, protocolVersion,
            adminEmails, earliestDatestamp,
            deletedRecord, granularity, compression)
        return identify

    def ListIdentifiers_impl(self, args, tree):
        namespaces = self.getNamespaces()
        def firstBatch():
            return self.buildIdentifiers(namespaces, tree)
        def nextBatch(token):
            tree = self.makeRequestErrorHandling(verb='ListIdentifiers',
                                                 resumptionToken=token)
            return self.buildIdentifiers(namespaces, tree)
        return ResumptionListGenerator(firstBatch, nextBatch)

    def ListMetadataFormats_impl(self, args, tree):
        namespaces = self.getNamespaces()
        evaluator = etree.XPathEvaluator(tree, namespaces)

        metadataFormat_nodes = evaluator.evaluate(
            '/oai:OAI-PMH/oai:ListMetadataFormats/oai:metadataFormat')
        metadataFormats = []
        for metadataFormat_node in metadataFormat_nodes:
            e = etree.XPathEvaluator(metadataFormat_node, namespaces).evaluate
            metadataPrefix = e('string(oai:metadataPrefix/text())')
            schema = e('string(oai:schema/text())')
            metadataNamespace = e('string(oai:metadataNamespace/text())')
            metadataFormat = (metadataPrefix, schema, metadataNamespace)
            metadataFormats.append(metadataFormat)

        return metadataFormats

    def ListRecords_impl(self, args, tree):
        namespaces = self.getNamespaces()
        metadata_prefix = args['metadataPrefix']
        metadata_registry = self._metadata_registry
        def firstBatch():
            return self.buildRecords(
                metadata_prefix, namespaces,
                metadata_registry, tree)
        def nextBatch(token):
            tree = self.makeRequestErrorHandling(
                verb='ListRecords',
                resumptionToken=token)
            return self.buildRecords(
                metadata_prefix, namespaces,
                metadata_registry, tree)
        return ResumptionListGenerator(firstBatch, nextBatch)

    def ListSets_impl(self, args, tree):
        namespaces = self.getNamespaces()
        def firstBatch():
            return self.buildSets(namespaces, tree)
        def nextBatch(token):
            tree = self.makeRequestErrorHandling(
                verb='ListSets',
                resumptionToken=token)
            return self.buildSets(namespaces, tree)
        return ResumptionListGenerator(firstBatch, nextBatch)

    # various helper methods
    
    def buildRecords(self,
                     metadata_prefix, namespaces, metadata_registry, tree):
        # first find resumption token if available
        evaluator = etree.XPathEvaluator(tree, namespaces)
        token = evaluator.evaluate(
            'string(/oai:OAI-PMH/*/oai:resumptionToken/text())')
        if token.strip() == '':
            token = None
        record_nodes = evaluator.evaluate(
            '/oai:OAI-PMH/*/oai:record')
        result = []
        for record_node in record_nodes:
            record_evaluator = etree.XPathEvaluator(record_node, namespaces)
            e = record_evaluator.evaluate
            # find header node
            header_node = e('oai:header')[0]
            # create header
            header = buildHeader(header_node, namespaces)
            # find metadata node
            metadata_list = e('oai:metadata')
            if metadata_list:
                metadata_node = metadata_list[0]
                # create metadata
                metadata = metadata_registry.readMetadata(metadata_prefix,
                                                          metadata_node)
            else:
                metadata = None
            # XXX TODO: about, should be third element of tuple
            result.append((header, metadata, None))
        return result, token

    def buildIdentifiers(self, namespaces, tree):
        evaluator = etree.XPathEvaluator(tree, namespaces)
        # first find resumption token is available
        token = evaluator.evaluate(
            'string(/oai:OAI-PMH/oai:ListIdentifiers/oai:resumptionToken/text())')
        if token.strip() == '':
            token = None    
        header_nodes = evaluator.evaluate(
                '/oai:OAI-PMH/oai:ListIdentifiers/oai:header')            
        result = []
        for header_node in header_nodes:
            header = buildHeader(header_node, namespaces)
            result.append(header)
        return result, token

    def buildSets(self, namespaces, tree):
        evaluator = etree.XPathEvaluator(tree, namespaces)
        # first find resumption token if available
        token = evaluator.evaluate(
            'string(/oai:OAI-PMH/oai:ListSets/oai:resumptionToken/text())')
        if token.strip() == '':
            token = None  
        set_nodes = evaluator.evaluate(
            '/oai:OAI-PMH/oai:ListSets/oai:set')
        sets = []
        for set_node in set_nodes:
            e = etree.XPathEvaluator(set_node, namespaces).evaluate
            setSpec = e('string(oai:setSpec/text())')
            setName = e('string(oai:setName/text())')
            # XXX setDescription nodes
            sets.append((setSpec, setName, None))
        return sets, token

    def makeRequestErrorHandling(self, **kw):
        xml = self.makeRequest(**kw)
        tree = self.parse(xml)
        # check whether there are errors first
        e_errors = tree.xpath('/oai:OAI-PMH/oai:error',
                              namespaces=self.getNamespaces())
        if e_errors:
            # XXX right now only raise first error found, does not
            # collect error info
            for e_error in e_errors:
                code = e_error.get('code')
                msg = e_error.text
                if code not in ['badArgument', 'badResumptionToken',
                                'badVerb', 'cannotDisseminateFormat',
                                'idDoesNotExist', 'noRecordsMatch',
                                'noMetadataFormats', 'noSetHierarchy']:
                    raise error.UnknownError,\
                          "Unknown error code from server: %s, message: %s" % (
                        code, msg)
                # find exception in error module and raise with msg
                raise getattr(error, code[0].upper() + code[1:] + 'Error'), msg
        return tree
    
    def makeRequest(self, **kw):
        raise NotImplementedError
    
class Client(BaseClient):
    def __init__(
            self, base_url, metadata_registry=None, credentials=None):
        BaseClient.__init__(self, metadata_registry)
        self._base_url = base_url
        if credentials is not None:
            self._credentials = base64.encodestring('%s:%s' % credentials)
        else:
            self._credentials = None
            
    def makeRequest(self, **kw):
        """Actually retrieve XML from the server.
        """
        # XXX include From header?
        headers = {'User-Agent': 'pyoai'}
        if self._credentials is not None:
            headers['Authorization'] = 'Basic ' + self._credentials.strip()
        request = urllib2.Request(
            self._base_url, data=urlencode(kw), headers=headers)
        return retrieveFromUrlWaiting(request)

def buildHeader(header_node, namespaces):
    e = etree.XPathEvaluator(header_node, namespaces).evaluate
    identifier = str(e('string(oai:identifier/text())'))
    datestamp = common.datestamp_to_datetime(
        str(e('string(oai:datestamp/text())')))
    setspec = [str(s) for s in e('oai:setSpec/text()')]
    deleted = e("@status = 'deleted'") 
    return common.Header(identifier, datestamp, setspec, deleted)

def ResumptionListGenerator(firstBatch, nextBatch):
    result, token = firstBatch()
    while 1:
        for item in result:
            yield item
        if token is None:
            break
        result, token = nextBatch(token)

def retrieveFromUrlWaiting(request,
                           wait_max=WAIT_MAX, wait_default=WAIT_DEFAULT):
    """Get text from URL, handling 503 Retry-After.
    """
    for i in range(wait_max):
        try:
            f = urllib2.urlopen(request)
            text = f.read()
            f.close()
            # we successfully opened without having to wait
            break
        except urllib2.HTTPError, e:
            if e.code == 503:
                try:
                    retryAfter = int(e.hdrs.get('Retry-After'))
                except ValueError:
                    retryAfter = None
                if retryAfter is None:
                    time.sleep(wait_default)
                else:
                    time.sleep(retryAfter)
            else:
                # reraise any other HTTP error
                raise
    else:
        raise Error, "Waited too often (more than %s times)" % wait_max
    return text

class ServerClient(BaseClient):
    def __init__(self, server, metadata_registry=None):
        BaseClient.__init__(self, metadata_registry)
        self._server = server
        
    def makeRequest(self, **kw):
        return self._server.handleRequest(kw)
