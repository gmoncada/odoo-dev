# -*- coding: utf-8 -*-
"""
The module :mod:`openerp.tests.common` provides unittest2 test cases and a few
helpers and classes to write tests.

"""
import json
import logging
import os
import select
import subprocess
import sys
import threading
import time
import unittest2
import uuid
import xmlrpclib

import openerp
from openerp import scope

_logger = logging.getLogger(__name__)

# The openerp library is supposed already configured.
ADDONS_PATH = openerp.tools.config['addons_path']
HOST = '127.0.0.1'
PORT = openerp.tools.config['xmlrpc_port']
DB = openerp.tools.config['db_name']

# If the database name is not provided on the command-line,
# use the one on the thread (which means if it is provided on
# the command-line, this will break when installing another
# database from XML-RPC).
if not DB and hasattr(threading.current_thread(), 'dbname'):
    DB = threading.current_thread().dbname

ADMIN_USER = 'admin'
ADMIN_USER_ID = openerp.SUPERUSER_ID
ADMIN_PASSWORD = 'admin'

HTTP_SESSION = {}

class BaseCase(unittest2.TestCase):
    """
    Subclass of TestCase for common OpenERP-specific code.
    
    This class is abstract and expects self.cr and self.uid to be initialized by subclasses.
    """

    @classmethod
    def cursor(self):
        return openerp.modules.registry.RegistryManager.get(DB).db.cursor()

    @classmethod
    def registry(self, model):
        return openerp.modules.registry.RegistryManager.get(DB)[model]

    @classmethod
    def ref(self, xid):
        """ Returns database ID corresponding to a given identifier.

            :param xid: fully-qualified record identifier, in the form ``module.identifier``
            :raise: ValueError if not found
        """
        assert "." in xid, "this method requires a fully qualified parameter, in the following form: 'module.identifier'"
        module, xid = xid.split('.')
        _, id = self.registry('ir.model.data').get_object_reference(self.cr, self.uid, module, xid)
        return id

    @classmethod
    def browse_ref(self, xid):
        """ Returns a browsable record for the given identifier.

            :param xid: fully-qualified record identifier, in the form ``module.identifier``
            :raise: ValueError if not found
        """
        assert "." in xid, "this method requires a fully qualified parameter, in the following form: 'module.identifier'"
        module, xid = xid.split('.')
        return self.registry('ir.model.data').get_object(self.cr, self.uid, module, xid)


class TransactionCase(BaseCase):
    """
    Subclass of BaseCase with a single transaction, rolled-back at the end of
    each test (method).
    """

    def setUp(self):
        # Store cr and uid in class variables, to allow ref() and browse_ref to be BaseCase @classmethods
        # and still access them
        TransactionCase.cr = cr = self.cursor()
        TransactionCase.uid = uid = openerp.SUPERUSER_ID
        TransactionCase.scope = scope(cr, uid, None).__enter__()

    def tearDown(self):
        self.scope.__exit__(None, None, None)
        self.cr.rollback()
        self.cr.close()


class SingleTransactionCase(BaseCase):
    """
    Subclass of BaseCase with a single transaction for the whole class,
    rolled-back after all the tests.
    """

    @classmethod
    def setUpClass(cls):
        cls.cr = cls.cursor()
        cls.uid = openerp.SUPERUSER_ID
        cls.scope = scope(cls.cr, cls.uid, None).__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.scope.__exit__(None, None, None)
        cls.cr.rollback()
        cls.cr.close()


class HttpCase(TransactionCase):
    """ Transactionnal HTTP TestCase with a phantomjs helper.
    """

    def __init__(self, methodName='runTest'):
        super(HttpCase, self).__init__(methodName)
        # v8 api with correct xmlrpc exception handling.
        self.xmlrpc_url = url_8 = 'http://%s:%d/xmlrpc/2/' % (HOST, PORT)
        self.xmlrpc_common = xmlrpclib.ServerProxy(url_8 + 'common')
        self.xmlrpc_db = xmlrpclib.ServerProxy(url_8 + 'db')
        self.xmlrpc_object = xmlrpclib.ServerProxy(url_8 + 'object')

    def setUp(self):
        super(HttpCase, self).setUp()
        self.session_id = uuid.uuid4().hex
        HTTP_SESSION[self.session_id] = self.cr

    def tearDown(self):
        del HTTP_SESSION[self.session_id]
        super(HttpCase, self).tearDown()

    def phantom_poll(self, phantom, timeout):
        """ Phantomjs Test protocol.

        Use console.log in phantomjs to output test results:

        - for a success: console.log("ok")
        - for an error:  console.log("error")

        Other lines are relayed to the test log.

        """
        t0 = time.time()
        buf = ''
        while 1:
            # timeout
            if time.time() > t0 + timeout:
                raise Exception("phantomjs test timeout (%ss)" % timeout)

            # read a byte
            ready, _, _ = select.select([phantom.stdout], [], [], 0.5)
            if ready:
                s = phantom.stdout.read(1)
                if s:
                    buf += s
                else:
                    break

            # process lines
            if '\n' in buf:
                line, buf = buf.split('\n', 1)
                _logger.info("phantomjs: %s", line)
                if line == "ok":
                    _logger.info("phantomjs test successful")
                    return
                if line == "error":
                    raise Exception("phantomjs test failed")

    def phantom_run(self, cmd, timeout):
        _logger.info('executing %s', cmd)
        try:
            phantom = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError:
            _logger.info("phantomjs not found, test %s skipped", jsfile)
        try:
            self.phantom_poll(phantom, timeout)
        finally:
            # kill phantomjs if phantom.exit() wasn't called in the test
            if phantom.poll() is None:
                phantom.terminate()

    def phantom_jsfile(self, jsfile, timeout=30, **kw):
        options = {
            'timeout' : timeout,
            'port': PORT,
            'db': DB,
            'session_id': self.session_id,
        }
        options.update(kw)
        phantomtest = os.path.join(os.path.dirname(__file__), 'phantomtest.js')
        # phantom.args[0] == phantomtest path
        # phantom.args[1] == options
        cmd = ['phantomjs', jsfile, phantomtest, json.dumps(options)]
        self.phantom_run(cmd, timeout)

    def phantom_js(self, url_path, code, ready="window", timeout=30, **kw):
        """ Test js code running in the browser
        - load page given by url_path
        - wait for ready object to be available
        - eval(code) inside the page

        To signal success test do:
        console.log('ok')

        To signal failure do:
        console.log('error')

        If neither are done before timeout test fails.
        """
        options = {
            'url_path': url_path,
            'code': code,
            'ready': ready,
            'timeout' : timeout,
            'port': PORT,
            'db': DB,
            'login': ADMIN_USER,
            'password': ADMIN_PASSWORD,
            'session_id': self.session_id,
        }
        options.update(kw)
        phantomtest = os.path.join(os.path.dirname(__file__), 'phantomtest.js')
        cmd = ['phantomjs', phantomtest, json.dumps(options)]
        self.phantom_run(cmd, timeout)


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
