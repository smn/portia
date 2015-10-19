import os
import json
import pkg_resources
from datetime import datetime, timedelta

from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase

from portia import utils
from portia.portia import Portia


class PortiaTest(TestCase):

    timeout = 1

    @inlineCallbacks
    def setUp(self):
        self.redis = yield utils.start_redis()
        self.portia = Portia(self.redis, network_prefix_mapping=json.load(
            pkg_resources.resource_stream(
                'portia', 'assets/network-prefix-mapping.json')))
        self.addCleanup(self.redis.disconnect)
        self.addCleanup(self.portia.flush)

    def fixture_path(self, fixture_name):
        return pkg_resources.resource_filename(
            'portia', os.path.join('tests', 'fixtures', fixture_name))

    @inlineCallbacks
    def test_import_filename(self):
        result = yield self.portia.import_porting_filename(
            self.fixture_path('sample-db.txt'))
        self.assertEqual(len(result), 10)

    @inlineCallbacks
    def test_import_porting_record(self):
        yield self.portia.import_porting_filename(
            self.fixture_path('sample-db.txt'))
        annotations = yield self.portia.get_annotations('27123456780')
        self.assertEqual(annotations['ported-to'], 'MNO2')
        self.assertEqual(annotations['ported-from'], 'MNO1')

    @inlineCallbacks
    def test_remove_imported_record(self):
        msisdn = yield self.portia.import_porting_record(
            '27123456789', 'DONOR', 'RECIPIENT', datetime.now().date())
        self.assertTrue((yield self.portia.get_annotations(msisdn)))
        self.assertTrue(
            (yield self.portia.remove_annotations(
                msisdn, 'ported-to', 'ported-from')))
        self.assertFalse((yield self.portia.get_annotations(msisdn)))

    @inlineCallbacks
    def test_flush(self):
        msisdn = yield self.portia.import_porting_record(
            '27123456789', 'DONOR', 'RECIPIENT', datetime.now())
        self.assertTrue((yield self.portia.get_annotations(msisdn)))
        self.assertTrue((yield self.portia.flush()))
        self.assertFalse((yield self.portia.get_annotations(msisdn)))

    @inlineCallbacks
    def test_annotate(self):
        timestamp1 = datetime.now()
        timestamp2 = datetime.now() - timedelta(days=1)
        yield self.portia.annotate(
            '27123456789', 'ported-to', 'MNO', timestamp=timestamp1)
        yield self.portia.annotate(
            '27123456789', 'X-foo', 'bar', timestamp=timestamp2)
        observation = yield self.portia.get_annotations(
            '27123456789')
        self.assertEqual(observation, {
            'ported-to': 'MNO',
            'ported-to-timestamp': timestamp1.isoformat(),
            'X-foo': 'bar',
            'X-foo-timestamp': timestamp2.isoformat()
        })

    @inlineCallbacks
    def test_remove_annotation(self):
        timestamp = datetime.now()
        yield self.portia.annotate(
            '27123456789', 'ported-to', 'MNO', timestamp=timestamp)
        yield self.portia.annotate(
            '27123456789', 'X-foo', 'bar', timestamp=timestamp)
        yield self.portia.annotate(
            '27123456789', 'X-xxx', '123', timestamp=timestamp)
        yield self.portia.remove_annotations(
            '27123456789', 'ported-to', 'X-xxx')
        observation = yield self.portia.get_annotations(
            '27123456789')
        self.assertEqual(observation, {
            'X-foo': 'bar',
            'X-foo-timestamp': timestamp.isoformat()
        })

    @inlineCallbacks
    def test_read_annotation(self):
        timestamp = datetime.now()
        yield self.portia.annotate(
            '27123456789', 'ported-to', 'MNO', timestamp=timestamp)
        yield self.portia.annotate(
            '27123456789', 'X-foo', 'bar', timestamp=timestamp)
        yield self.portia.annotate(
            '27123456789', 'X-xxx', '123', timestamp=timestamp)
        self.assertEqual(
            (yield self.portia.read_annotation('27123456789', 'ported-to')),
            {
                'ported-to': 'MNO',
                'ported-to-timestamp': timestamp.isoformat(),
            })

    @inlineCallbacks
    def test_remove(self):
        msisdn = yield self.portia.import_porting_record(
            '27123456789', 'DONOR', 'RECIPIENT', datetime.now())
        # Removal should return True
        self.assertTrue((yield self.portia.remove(msisdn)))
        # Now, nothing's being removed, should return False
        self.assertFalse((yield self.portia.remove(msisdn)))

    @inlineCallbacks
    def test_resolve_porting_db(self):
        msisdn = yield self.portia.import_porting_record(
            '27123456789', 'DONOR', 'RECIPIENT', datetime.now())
        result = yield self.portia.resolve(msisdn)
        self.assertEqual(result['network'], 'RECIPIENT')
        self.assertEqual(result['strategy'], 'ported-to')

    @inlineCallbacks
    def test_resolve_observation(self):
        yield self.portia.annotate(
            '27123456789', 'observed-network', 'MNO')
        result = yield self.portia.resolve('27123456789')
        self.assertEqual(result['network'], 'MNO')
        self.assertEqual(result['strategy'], 'observed-network')

    @inlineCallbacks
    def test_resolve_prefix_guess(self):
        result = yield self.portia.resolve('27763456789')
        self.assertEqual(result['network'], 'VODACOM')
        self.assertEqual(result['strategy'], 'prefix-guess')

    @inlineCallbacks
    def test_resolve_prefix_guess_unknown(self):
        result = yield self.portia.resolve('000000000000')
        self.assertEqual(result['network'], None)
        self.assertEqual(result['strategy'], 'prefix-guess')
