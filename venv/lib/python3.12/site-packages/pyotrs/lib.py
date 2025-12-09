""" lib.py

PyOTRS lib

This code implements the PyOTRS library to provide access to the OTRS API (REST)
"""

import base64
import datetime
import json
import logging
import mimetypes
import os
import time

import deprecation
import requests

from .version import __version__

log = logging.getLogger(__name__)

TICKET_CONNECTOR_CONFIG_DEFAULT = {
    'Name': 'GenericTicketConnectorREST',
    'Config': {
        'SessionCreate': {'RequestMethod': 'POST',
                          'Route': '/Session',
                          'Result': 'SessionID'},
        'AccessTokenCreate': {'RequestMethod': 'POST',
                              'Route': '/Session',
                              'Result': 'AccessToken'},
        'SessionGet': {'RequestMethod': 'GET',
                       'Route': '/Session/:SessionID',
                       'Result': 'SessionData'},
        'TicketCreate': {'RequestMethod': 'POST',
                         'Route': '/Ticket',
                         'Result': 'TicketID'},
        'TicketGet': {'RequestMethod': 'GET',
                      'Route': '/Ticket/:TicketID',
                      'Result': 'Ticket'},
        'TicketGetList': {'RequestMethod': 'GET',
                          'Route': '/TicketList',
                          'Result': 'Ticket'},
        'TicketHistoryGet': {'RequestMethod': 'GET',
                             'Route': '/TicketHistory/:TicketID',
                             'Result': 'TicketHistory'},
        'TicketSearch': {'RequestMethod': 'GET',
                         'Route': '/Ticket',
                         'Result': 'TicketID'},
        'TicketUpdate': {'RequestMethod': 'PATCH',
                         'Route': '/Ticket/:TicketID',
                         'Result': 'TicketID'},
    }
}

LINK_CONNECTOR_CONFIG_DEFAULT = {
    'Name': 'GenericLinkConnectorREST',
    'Config': {
        'LinkAdd': {'RequestMethod': 'POST',
                    'Route': '/LinkAdd',
                    'Result': 'LinkAdd'},
        'LinkDelete': {'RequestMethod': 'DELETE',
                       'Route': '/LinkDelete',
                       'Result': 'LinkDelete'},
        'LinkDeleteAll': {'RequestMethod': 'DELETE',
                          'Route': '/LinkDeleteAll',
                          'Result': 'LinkDeleteAll'},
        'LinkList': {'RequestMethod': 'GET',
                     'Route': '/LinkList',
                     'Result': 'LinkList'},
        'PossibleLinkList': {'RequestMethod': 'GET',
                             'Route': '/PossibleLinkList',
                             'Result': 'PossibleLinkList'},
        'PossibleObjectsList': {'RequestMethod': 'GET',
                                'Route': '/PossibleObjectsList',
                                'Result': 'PossibleObject'},
        'PossibleTypesList': {'RequestMethod': 'GET',
                              'Route': '/PossibleTypesList',
                              'Result': 'PossibleType'},
    }
}

# Check if OS is Linux or Windows (#47):
OS_TYPE_WINDOWS = False
try:
    from platform import system

    if 'Windows' in system():
        OS_TYPE_WINDOWS = True
        log.debug("OS Type: Windows")
    else:
        log.debug("OS Type: Linux")
except:  # noqa: E722
    log.warning("Could not determine OS-Type (Linux/Windows). Using default: 'Linux'.")


class PyOTRSError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class ArgumentMissingError(PyOTRSError):
    pass


class ArgumentInvalidError(PyOTRSError):
    pass


class ResponseParseError(PyOTRSError):
    pass


class SessionCreateError(PyOTRSError):
    pass


class SessionNotCreated(PyOTRSError):  # noqa: N818
    pass


class APIError(PyOTRSError):
    pass


class HTTPError(PyOTRSError):
    pass


class Article:
    """PyOTRS Article class """

    def __init__(self, dct):
        fields = {}
        for key, _value in dct.items():
            fields.update({key: dct[key]})

        try:
            self.aid = int(fields.get("ArticleID"))
        except TypeError:
            self.aid = 0

        self.fields = fields

        self.attachments = self._parse_attachments()
        self.fields.pop("Attachment", None)

        self.dynamic_fields = self._parse_dynamic_fields()
        self.fields.pop("DynamicField", None)

    def __repr__(self):
        if self.aid != 0:
            _len = len(self.attachments)
            if _len == 0:
                return f"<ArticleID: {self.aid}>"
            elif _len == 1:
                return f"<ArticleID: {self.aid} (1 Attachment)>"
            else:
                return f"<ArticleID: {self.aid} ({_len} Attachments)>"
        else:
            return f"<{self.__class__.__name__}>"

    def to_dct(self, attachments=True, attachment_cont=True, dynamic_fields=True):
        """represent as nested dict compatible for OTRS

        Args:
            attachments (bool): if True will include, otherwise exclude:
                "Attachment" (default: True)
            attachment_cont (bool): if True will include, otherwise exclude:
                "Attachment" > "Content" (default: True)
            dynamic_fields (bool): if True will include, otherwise exclude:
                "DynamicField" (default: True)

        Returns:
            **dict**: Article represented as dict for OTRS

        """
        dct = {}

        if attachments:
            if self.attachments:
                dct.update({"Attachment": [x.to_dct(content=attachment_cont) for x in
                                           self.attachments]})

        if dynamic_fields:
            if self.dynamic_fields:
                dct.update({"DynamicField": [x.to_dct() for x in self.dynamic_fields]})

        if self.fields:
            dct.update(self.fields)

        return dct

    def _parse_attachments(self):
        """parse Attachment from Ticket and return as **list** of **Attachment** objects"""
        lst = self.fields.get("Attachment")
        if lst:
            return [Attachment(item) for item in lst]
        else:
            return []

    def _parse_dynamic_fields(self):
        """parse DynamicField from Ticket and return as **list** of **DynamicField** objects"""
        lst = self.fields.get("DynamicField")
        if lst:
            return [DynamicField.from_dct(item) for item in lst]
        else:
            return []

    def attachment_get(self, a_filename):
        """attachment_get

        Args:
            a_filename (str): Filename of Attachment to retrieve

        Returns:
            **Attachment** or **None**

        """
        result = [x for x in self.attachments if x.Filename == f"{a_filename}"]
        if result:
            return result[0]
        else:
            return None

    def dynamic_field_get(self, df_name):
        """dynamic_field_get

        Args:
            df_name (str): Name of DynamicField to retrieve

        Returns:
            **DynamicField** or **None**

        """

        result = [x for x in self.dynamic_fields if x.name == f"{df_name}"]
        if result:
            return result[0]
        else:
            return None

    def field_get(self, f_name):
        return self.fields.get(f_name)

    def validate(self, validation_map=None):
        """validate data against a mapping dict - if a key is not present
        then set it with a default value according to dict

        Args:
            validation_map (dict): A mapping for all Article fields that have to be set. During
            validation every required field that is not set will be set to a default value
            specified in this dict.

        .. note::
            There is also a blacklist (fields to be removed) but this is currently
            hardcoded to *dynamic_fields* and *attachments*.

        """
        if not validation_map:
            validation_map = {"Body": "API created Article Body",
                              "Charset": "UTF8",
                              "MimeType": "text/plain",
                              "Subject": "API created Article",
                              "TimeUnit": 0}

        for key, value in validation_map.items():
            if not self.fields.get(key, None):
                self.fields.update({key: value})

    @classmethod
    def _dummy(cls):
        """dummy data (for testing)

        Returns:
            **Article**: An Article object.

        """
        return Article({"Subject": "Dümmy Subject",
                        "Body": "Hallo Bjørn,\n[kt]\n\n -- The End",
                        "TimeUnit": 0,
                        "MimeType": "text/plain",
                        "Charset": "UTF8"})

    @classmethod
    def _dummy_force_notify(cls):
        """dummy data (for testing)

        Returns:
            **Article**: An Article object.

        """
        return Article({"Subject": "Dümmy Subject",
                        "Body": "Hallo Bjørn,\n[kt]\n\n -- The End",
                        "TimeUnit": 0,
                        "MimeType": "text/plain",
                        "Charset": "UTF8",
                        "ForceNotificationToUserID": [1, 2]})


class Attachment:
    """PyOTRS Attachment class """

    def __init__(self, dct):
        self.__dict__ = dct

    def __repr__(self):
        if hasattr(self, 'Filename'):
            return f"<{self.__class__.__name__}: {self.Filename}>"
        else:
            return f"<{self.__class__.__name__}>"

    def to_dct(self, content=True):
        """represent Attachment object as dict
        Args:
            content (bool): if True will include, otherwise exclude: "Content" (default: True)

        Returns:
            **dict**: Attachment represented as dict.

        """
        dct = self.__dict__
        if content:
            return dct
        else:
            dct.pop("Content")
            return dct

    @classmethod
    def create_basic(cls, Content=None, ContentType=None, Filename=None):  # noqa: N803
        """create a basic Attachment object

        Args:
            Content (str): base64 encoded content
            ContentType (str): MIME type of content (e.g. text/plain)
            Filename (str): file name (e.g. file.txt)


        Returns:
            **Attachment**: An Attachment object.

        """
        return Attachment({'Content': Content,
                           'ContentType': ContentType,
                           'Filename': Filename})

    @classmethod
    def create_from_file(cls, file_path):
        """save Attachment to a folder on disc

        Args:
            file_path (str): The full path to the file from which an Attachment should be created.

        Returns:
            **Attachment**: An Attachment object.

        """
        with open(file_path, 'rb') as f:
            content = f.read()

        content_type = mimetypes.guess_type(file_path)[0]
        if not content_type:
            content_type = "application/octet-stream"
        return Attachment({'Content': base64.b64encode(content).decode('utf-8'),
                           'ContentType': content_type,
                           'Filename': os.path.basename(file_path)})

    def save_to_dir(self, folder="/tmp"):
        """save Attachment to a folder on disc

        Args:
            folder (str): The directory where this attachment should be saved to.

        Returns:
            **bool**: True

        """
        if not hasattr(self, 'Content') or not hasattr(self, 'Filename'):
            raise ValueError("invalid Attachment")

        file_path = os.path.join(os.path.abspath(folder), self.Filename)
        with open(file_path, 'wb') as f:
            f.write(base64.b64decode(self.Content))

        return True

    @classmethod
    def _dummy(cls):
        """dummy data (for testing)

        Returns:
            **Attachment**: An Attachment object.

        """
        return Attachment.create_basic("YmFyCg==", "text/plain", "dümmy.txt")


class DynamicField:
    """PyOTRS DynamicField class

    Args:
        name (str): Name of OTRS DynamicField (required)
        value (str): Value of OTRS DynamicField
        search_operator (str): Search operator (defaults to: "Equals")
            Valid options are:
            "Equals", "Like", "GreaterThan", "GreaterThanEquals",
            "SmallerThan", "SmallerThanEquals"
        search_patterns (list): List of patterns (str or datetime) to search for

    """

    SEARCH_OPERATORS = ("Equals", "Like", "GreaterThan", "GreaterThanEquals",
                        "SmallerThan", "SmallerThanEquals",)

    def __init__(self, name, value=None, search_patterns=None, search_operator="Equals"):
        self.name = name
        self.value = value

        if not isinstance(search_patterns, list):
            self.search_patterns = [search_patterns]
        else:
            self.search_patterns = search_patterns

        if search_operator not in DynamicField.SEARCH_OPERATORS:
            raise NotImplementedError(f"Invalid Operator: \"{search_operator}\"")
        self.search_operator = search_operator

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}: {self.value}>"

    @classmethod
    def from_dct(cls, dct):
        """create DynamicField from dct

        Args:
            dct (dict):

        Returns:
            **DynamicField**: A DynamicField object.

        """
        return cls(name=dct["Name"], value=dct["Value"])

    def to_dct(self):
        """represent DynamicField as dict

        Returns:
            **dict**: DynamicField as dict.

        """
        return {"Name": self.name, "Value": self.value}

    def to_dct_search(self):
        """represent DynamicField as dict for search operations

        Returns:
            **dict**: DynamicField as dict for search operations

        """
        _lst = []
        for item in self.search_patterns:
            if isinstance(item, datetime.datetime):
                item = item.strftime("%Y-%m-%d %H:%M:%S")
            _lst.append(item)

        return {f"DynamicField_{self.name}": {self.search_operator: _lst}}

    @classmethod
    def _dummy1(cls):
        """dummy1 data (for testing)

        Returns:
            **DynamicField**: A list of DynamicField objects.

        """
        return DynamicField(name="firstname", value="Jane")

    @classmethod
    def _dummy2(cls):
        """dummy2 data (for testing)

        Returns:
            **DynamicField**: A list of DynamicField objects.

        """
        return DynamicField.from_dct({'Name': 'lastname', 'Value': 'Doe'})


class Ticket:
    """PyOTRS Ticket class

        Args:
           tid (int): OTRS Ticket ID as integer
           fields (dict): OTRS Top Level fields
           articles (list): List of Article objects
           dynamic_fields (list): List of DynamicField objects

    """

    def __init__(self, dct):
        # store OTRS Top Level fields
        self.fields = {}
        self.fields.update(dct)

        self.tid = int(self.fields.get("TicketID", 0))
        self.articles = self._parse_articles()
        self.fields.pop("Article", None)

        self.dynamic_fields = self._parse_dynamic_fields()
        self.fields.pop("DynamicField", None)

    def __repr__(self):
        if self.tid:
            return f"<{self.__class__.__name__}: {self.tid}>"
        else:
            return f"<{self.__class__.__name__}>"

    def _parse_articles(self):
        """parse Article from Ticket and return as **list** of **Article** objects"""
        lst = self.fields.get("Article", [])
        return [Article(item) for item in lst]

    def _parse_dynamic_fields(self):
        """parse DynamicField from Ticket and return as **list** of **DynamicField** objects"""
        lst = self.fields.get("DynamicField", [])
        return [DynamicField.from_dct(item) for item in lst]

    def to_dct(self,
               articles=True,
               article_attachments=True,
               article_attachment_cont=True,
               article_dynamic_fields=True,
               dynamic_fields=True):
        """represent as nested dict

        Args:
            articles (bool): if True will include, otherwise exclude:
                "Article" (default: True)
            article_attachments (bool): if True will include, otherwise exclude:
                "Article" > "Attachment" (default: True)
            article_attachment_cont (bool): if True will include, otherwise exclude:
                "Article" > "Attachment" > "Content" (default: True)
            article_dynamic_fields (bool): if True will include, otherwise exclude:
                "Article" > "DynamicField" (default: True)
            dynamic_fields (bool): if True will include, otherwise exclude:
                "DynamicField" (default: True)

        Returns:
            **dict**: Ticket represented as dict.

        .. note::
            Does not contain Articles or DynamicFields (currently)

        """
        dct = {}
        dct.update(self.fields)

        if articles:
            try:
                if self.articles:
                    dct.update({"Article": [x.to_dct(attachments=article_attachments,
                                                     attachment_cont=article_attachment_cont,
                                                     dynamic_fields=article_dynamic_fields)
                                            for x in self.articles]})
            except AttributeError:
                pass

        if dynamic_fields:
            try:
                if self.dynamic_fields:
                    dct.update({"DynamicField": [x.to_dct() for x in self.dynamic_fields]})
            except AttributeError:
                pass

        return {"Ticket": dct}

    def article_get(self, aid):
        """article_get

        Args:
            aid (str): Article ID as either int or str

        Returns:
            **Article** or **None**

        """
        result = [x for x in self.articles if x.field_get("ArticleID") == str(aid)]
        return result[0] if result else None

    def dynamic_field_get(self, df_name):
        """dynamic_field_get

        Args:
            df_name (str): Name of DynamicField to retrieve

        Returns:
            **DynamicField** or **None**

        """
        result = [x for x in self.dynamic_fields if x.name == df_name]
        return result[0] if result else None

    def field_get(self, f_name):
        return self.fields.get(f_name)

    def field_add(self, fields=None, **kwargs):
        """add fields to ticket

        Provide a dictionary of key:value pairs to be added to the ticket,
        e.g. the basic ticket.

        Use it like `field_add({"SLA": "1h", "Service": "Ticket-Service"})` or via kwargs
        by providing key=value pairs: `field_add(SLA="1h", Service="Ticket-Service")`.

        Args:
            fields (dict): Dictionary of new fields to be added to the
                           Ticket instance.

        Returns:
            **dict**: The current fields attribute of the ticket.

        """
        if isinstance(fields, dict):
            self.fields.update(fields)

        if kwargs and isinstance(kwargs, dict):
            self.fields.update(kwargs)

        return self.fields

    @classmethod
    def create_basic(cls,
                     Title=None,  # noqa: N803
                     QueueID=None,  # noqa: N803
                     Queue=None,  # noqa: N803
                     TypeID=None,  # noqa: N803
                     Type=None,  # noqa: N803
                     StateID=None,  # noqa: N803
                     State=None,  # noqa: N803
                     PriorityID=None,  # noqa: N803
                     Priority=None,  # noqa: N803
                     CustomerUser=None):  # noqa: N803
        """create basic ticket

        Args:
            Title (str): OTRS Ticket Title
            QueueID (str): OTRS Ticket QueueID (e.g. "1")
            Queue (str): OTRS Ticket Queue (e.g. "raw")
            TypeID (str): OTRS Ticket TypeID (e.g. "1")
            Type (str): OTRS Ticket Type (e.g. "Problem")
            StateID (str): OTRS Ticket StateID (e.g. "1")
            State (str): OTRS Ticket State (e.g. "open" or "new")
            PriorityID (str): OTRS Ticket PriorityID (e.g. "1")
            Priority (str): OTRS Ticket Priority (e.g. "low")
            CustomerUser (str): OTRS Ticket CustomerUser

        Returns:
            **Ticket**: A new Ticket object.

        """
        if not Title:
            raise ArgumentMissingError("Title is required")

        if not Queue and not QueueID:
            raise ArgumentMissingError("Either Queue or QueueID required")

        if not State and not StateID:
            raise ArgumentMissingError("Either State or StateID required")

        if not Priority and not PriorityID:
            raise ArgumentMissingError("Either Priority or PriorityID required")

        if not CustomerUser:
            raise ArgumentMissingError("CustomerUser is required")

        if Type and TypeID:
            raise ArgumentInvalidError("Either Type or TypeID - not both")

        dct = {"Title": Title}

        if Queue:
            dct.update({"Queue": Queue})
        else:
            dct.update({"QueueID": QueueID})

        if Type:
            dct.update({"Type": Type})
        if TypeID:
            dct.update({"TypeID": TypeID})

        if State:
            dct.update({"State": State})
        else:
            dct.update({"StateID": StateID})

        if Priority:
            dct.update({"Priority": Priority})
        else:
            dct.update({"PriorityID": PriorityID})

        dct.update({"CustomerUser": CustomerUser})

        for key, value in dct.items():
            dct.update({key: value})

        return Ticket(dct)

    @classmethod
    def _dummy(cls):
        """dummy data (for testing)

        Returns:
            **Ticket**: A Ticket object.

        """
        return Ticket.create_basic(Queue="Raw",
                                   State="open",
                                   Priority="3 normal",
                                   CustomerUser="root@localhost",
                                   Title="Bäsic Ticket")

    @staticmethod
    def datetime_to_pending_time_text(datetime_object=None):
        """datetime_to_pending_time_text

        Args:
            datetime_object (Datetime)

        Returns:
            **str**: The pending time in the format required for OTRS REST interface.

        """
        return {
            "Year": datetime_object.year,
            "Month": datetime_object.month,
            "Day": datetime_object.day,
            "Hour": datetime_object.hour,
            "Minute": datetime_object.minute
        }


class SessionStore:
    """Session ID: persistently store to and retrieve from to file

    Args:
        file_path (str): Path on disc
        session_timeout (int): OTRS Session Timeout Value (to avoid reusing outdated session id
        value (str): A Session ID as str
        created (int): seconds as epoch when a session_id record was created
        expires (int): seconds as epoch when a session_id record expires
        is_legacy (bool): whether the Session ID is for an older OTRS Version (<=7)

    Raises:
        ArgumentMissingError

    """

    def __init__(self, file_path=None, session_timeout=None,
                 value=None, created=None, expires=None, is_legacy=False):
        if not file_path:
            raise ArgumentMissingError("Argument file_path is required!")

        if not session_timeout:
            raise ArgumentMissingError("Argument session_timeout is required!")

        self.file_path = file_path
        self.timeout = session_timeout
        self.value = value
        self.created = created
        self.expires = expires
        self.is_legacy = is_legacy

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.file_path}>"

    def read(self):
        """Retrieve a stored Session ID from file

        Returns:
            **str** or **None**: Retrieved Session ID or None (if none could be read)

        """
        if not os.path.isfile(self.file_path):
            return None

        if not SessionStore._validate_file_owner_and_permissions(self.file_path):
            return None

        with open(self.file_path) as f:
            content = f.read()
        try:
            data = json.loads(content)
            self.value = data['session_id']
            self.is_legacy = data.get('is_legacy', False)

            self.created = datetime.datetime.utcfromtimestamp(int(data['created']))
            self.expires = (self.created + datetime.timedelta(seconds=self.timeout))

            if self.expires > datetime.datetime.utcnow():
                return self.value  # still valid
        except ValueError:
            return None
        except KeyError:
            return None
        except Exception as err:
            raise Exception(f"Exception Type: {type(err)}: {err}")

    def write(self, new_value):
        """Write and store a Session ID to file (rw for user only)

        Args:
            new_value (str): if none then empty value will be writen to file
        Returns:
            **bool**: **True** if successful, False **otherwise**.

        """
        self.value = new_value

        if os.path.isfile(self.file_path):
            if not SessionStore._validate_file_owner_and_permissions(self.file_path):
                raise OSError("File exists but is not ok (wrong owner/permissions)!")

        with open(self.file_path, 'w') as f:
            f.write(json.dumps({'created': str(int(time.time())),
                                'session_id': self.value,
                                'is_legacy': self.is_legacy}))
        os.chmod(self.file_path, 384)  # 384 is '0600'

        # TODO 2016-04-23 (RH): check this
        if not SessionStore._validate_file_owner_and_permissions(self.file_path):
            raise OSError("Race condition: Something happened to file during the run!")

        return True

    def delete(self):
        """remove session id file (e.g. when it only contains an invalid session id)

        Raises:
            NotImplementedError

        Returns:
            **bool**: **True** if successful, otherwise **False**.

        .. todo::
            (RH) implement this _remove_session_id_file
        """
        raise NotImplementedError("Not yet done")

    @staticmethod
    def _validate_file_owner_and_permissions(full_file_path):
        """validate SessionStore file ownership and permissions

        Args:
            full_file_path (str): full path to file on disc

        Returns:
            **bool**: **True** if valid and correct (or running on Windows), otherwise **False**...

        """
        if not os.path.isfile(full_file_path):
            raise OSError(f"Does not exist or not a file: {full_file_path}")

        if OS_TYPE_WINDOWS:  # We have to do this, as os.getuid() is not defined if run on Windows
            return True

        file_lstat = os.lstat(full_file_path)
        if not file_lstat.st_uid == os.getuid():
            return False

        if not file_lstat.st_mode & 0o777 == 384:
            """ check for unix permission User R+W only (0600)
            >>> oct(384)
            '0600' Python 2
            >>> oct(384)
            '0o600' Python 3  """
            return False

        return True


class Client:
    """PyOTRS Client class - includes Session handling

    Args:
        baseurl (str): Base URL for OTRS System, no trailing slash e.g. http://otrs.example.com
        username (str): Username
        password (str): Password
        session_id_file (str): Session ID path on disc, used to persistently store Session ID
        session_timeout (int): Session Timeout configured in OTRS (usually 28800 seconds = 8h)
        session_validation_ticket_id (int): Ticket ID of an existing ticket - used to perform
            several check - e.g. validate log in (defaults to 1)
        webservice_config_ticket (dict): OTRS REST Web Service Name - Ticket Connector
        webservice_config_faq (dict): OTRS REST Web Service Name - FAQ Connector (FAQ code was
            deprecated in 0.4.0 and removed in 1.0.0 - parameter stays for compatibility)
        webservice_config_link (dict): OTRS REST Web Service Name - Link Connector
        proxies (dict): Proxy settings - refer to requests docs for
            more information - default to no proxies
        https_verify (bool): Should HTTPS certificates be verified (defaults to True)
        ca_cert_bundle (str): file path - if specified overrides python/system default for
            Root CA bundle that will be used.
        auth (tuple): e.g. ("user", "pass") - see requests documentation ("auth") for details
        client_auth_cert (str): file path containing both certificate and key (unencrypted) in
            PEM format to use for TLS client authentication (passed to requests as "cert")
        customer_user (bool): flag to indicate that the username is for a "CustomerUser"
           (defaults to False)
        user_agent (str): optional HTTP UserAgent string
        webservice_path (str): OTRS REST Web Service Path part - defaults to
            "/otrs/nph-genericinterface.pl/Webservice/"
        use_legacy_sessions (bool): if True, use sessions compatibility for OTRS < V8
        request_timeout (float or tuple): optional How many seconds to wait for the server
            to send data before giving up, as a float, or a (connect timeout, read timeout) tuple

    """

    def __init__(self,
                 baseurl=None,
                 username=None,
                 password=None,
                 session_id_file=None,
                 session_timeout=None,
                 session_validation_ticket_id=1,
                 webservice_config_ticket=None,
                 webservice_config_faq=None,
                 webservice_config_link=None,
                 proxies=None,
                 https_verify=True,
                 ca_cert_bundle=None,
                 auth=None,
                 client_auth_cert=None,
                 customer_user=False,
                 user_agent=None,
                 webservice_path="/otrs/nph-genericinterface.pl/Webservice/",
                 use_legacy_sessions=False,
                 request_timeout=None
                 ):

        if not baseurl:
            raise ArgumentMissingError("baseurl")
        self.baseurl = baseurl.rstrip("/")
        self.webservice_path = webservice_path

        if not session_timeout:
            self.session_timeout = 28800  # 8 hours is OTRS default
        else:
            self.session_timeout = session_timeout

        if not session_id_file:
            if OS_TYPE_WINDOWS:
                # No '/tmp/...' available on Windows OS, so using in Windows Temp folder instead
                p = os.path.expanduser('~\\AppData\\Local\\Temp\\.pyotrs_session_id')
                session_id_path = p
            else:
                session_id_path = "/tmp/.pyotrs_session_id"  # Default for Linux

            self.session_id_store = SessionStore(file_path=session_id_path,
                                                 session_timeout=self.session_timeout,
                                                 is_legacy=use_legacy_sessions)
        else:
            self.session_id_store = SessionStore(file_path=session_id_file,
                                                 session_timeout=self.session_timeout,
                                                 is_legacy=use_legacy_sessions)

        self.session_validation_ticket_id = session_validation_ticket_id

        # A dictionary for mapping OTRS WebService operations to HTTP Method, Route and
        # Result string.
        if not webservice_config_ticket:
            webservice_config_ticket = TICKET_CONNECTOR_CONFIG_DEFAULT

        if not webservice_config_link:
            webservice_config_link = LINK_CONNECTOR_CONFIG_DEFAULT

        self.ws_ticket = webservice_config_ticket['Name']
        self.ws_link = webservice_config_link['Name']

        self.routes_ticket = [x[1]["Route"] for x in webservice_config_ticket['Config'].items()]
        self.routes_link = [x[1]["Route"] for x in webservice_config_link['Config'].items()]

        webservice_config = {}
        webservice_config.update(webservice_config_ticket['Config'])
        webservice_config.update(webservice_config_link['Config'])
        self.ws_config = webservice_config

        if not proxies:
            self.proxies = {"http": "", "https": "", "no": ""}
        else:
            if not isinstance(proxies, dict):
                raise ValueError("Proxy settings need to be provided as dict!")
            self.proxies = proxies

        if https_verify:
            if not ca_cert_bundle:
                self.https_verify = https_verify
            else:
                ca_certs = os.path.abspath(ca_cert_bundle)
                if not os.path.isfile(ca_certs):
                    raise ValueError(f"Certificate file does not exist: {ca_certs}")
                self.https_verify = ca_certs
        else:
            self.https_verify = False

        self.auth = auth
        self.client_auth_cert = client_auth_cert
        self.request_timeout = request_timeout

        self.customer_user = customer_user

        self.user_agent = user_agent

        self.use_legacy_sessions = use_legacy_sessions

        # credentials
        self.username = username
        self.password = password

        # dummy initialization
        self.operation = None
        self.result_json = None
        self.result = []

    """
    Returns the correct session key to look for/send based
    on the current session compatibility level
    for legacy sessions (< OTRS V8) this returns 'SessionID'
    from V8 onwards this returns 'AccessToken'
    """

    @property
    def _session_key(self):
        if self.use_legacy_sessions:
            return 'SessionID'
        else:
            return 'AccessToken'

    """
    GenericInterface::Operation::Session::SessionCreate
        * session_check_is_valid
        * session_create
        * session_get
        * session_restore_or_set_up_new  # try to get session_id from a (json) file on disc
    """

    @deprecation.deprecated(deprecated_in="0.10.0", removed_in="2.0", current_version=__version__,
                            details="This method was implemented with a \"dirty\" workaround and "
                                    "should not be called anymore. Use Client.session_get() "
                                    "instead. ATTENTION: Using session_get() requires the OTRS "
                                    "route for HTTP GET /Session to be configured  (which is/was "
                                    "not the default).")
    def session_check_is_valid(self, session_id=None):
        """check whether session_id is currently valid

        Args:
            session_id (str): optional if set overrides the self.session_id

        Raises:
            ArgumentMissingError: if session_id is not set

        Returns:
            **bool**: **True** if valid, otherwise **False**.

        .. note::
            Uses HTTP Method: GET
        """
        self.operation = "TicketGet"

        if not session_id:
            raise ArgumentMissingError("session_id")

        # TODO 2016-04-13 (RH): Is there a nicer way to check whether session is valid?!
        payload = {self._session_key: session_id}

        response = self._send_request(payload, data_id=self.session_validation_ticket_id)
        return self._parse_and_validate_response(response)

    def session_create(self):
        """create new (temporary) session (and Session ID)

        Returns:
            **bool**: **True** if successful, otherwise **False**.

        .. note::
            Session ID is recorded in self.session_id_store.value (**non persistently**)

        .. note::
            Uses HTTP Method: POST

        """
        if self.use_legacy_sessions:
            self.operation = "SessionCreate"
        else:
            self.operation = "AccessTokenCreate"

        if self.customer_user:
            payload = {
                "CustomerUserLogin": self.username,
                "Password": self.password
            }
        else:
            payload = {
                "UserLogin": self.username,
                "Password": self.password
            }

        response = self._send_request(payload)
        try:
            if not self._parse_and_validate_response(response):
                return False
        except ResponseParseError:
            if not self.use_legacy_sessions:
                log.warning("AccessTokenCreate failed, retrying using legacy session")
                self.use_legacy_sessions = True
                self.session_id_store.is_legacy = True
                return self.session_create()
            return False

        self.session_id_store.value = self.result_json[self._session_key]
        return True

    def session_get(self, session_id=None):
        """get/check/validate a Session ID

        Returns:
            **bool**: **True** if successful, otherwise **False**.

        .. note::
            Uses HTTP Method: GET

        """
        self.operation = "SessionGet"

        if not session_id:
            raise ArgumentMissingError("session_id")

        payload = {self._session_key: session_id}

        response = self._send_request(payload, data_id=session_id)
        return self._parse_and_validate_response(response)

    def session_restore_or_create(self):
        """Try to restore Session ID from file otherwise create new one and save to file

        Raises:
            SessionCreateError
            SessionIDFileError

        .. note::
            Session ID is recorded in self.session_id_store.value (**non persistently**)

        .. note::
            Session ID is **saved persistently** to file: *self.session_id_store.file_path*

        Returns:
            **bool**: **True** if successful, otherwise **False**.
        """
        # try to read session_id from file
        self.session_id_store.value = self.session_id_store.read()

        if self.session_id_store.value:
            # got one.. use stored is_legacy status info
            self.use_legacy_sessions = self.session_id_store.is_legacy
            # and the check whether it's still valid
            if self.session_get(self.session_id_store.value):
                log.info("Using valid Session ID "
                         f"from ({self.session_id_store.file_path})")
                return True

        # got no (valid) session_id; clean store
        self.session_id_store.write("")

        # and try to create new one
        if not self.session_create():
            raise SessionCreateError("Failed to create a Session ID!")

        # save new created session_id to file
        if not self.session_id_store.write(self.result_json[self._session_key]):
            raise OSError("Failed to save Session ID to file!")
        else:
            log.info("Saved new Session ID to file: "
                     f"{self.session_id_store.file_path}")
            return True

    @deprecation.deprecated(deprecated_in="0.10.0", removed_in="2.0", current_version=__version__,
                            details="This method uses session_check_is_valid which was "
                                    "implemented with a \"dirty\" workaround and should not be "
                                    "called anymore. Use Client.session_restore_or_create() "
                                    "instead. ATTENTION: Using that also switches to "
                                    "session_get() which requires the OTRS route for HTTP GET "
                                    "/Session to be configured  (which is/was not the default).")
    def session_restore_or_set_up_new(self):
        """Try to restore Session ID from file otherwise create new one and save to file

        Raises:
            SessionCreateError
            SessionIDFileError

        .. note::
            Session ID is recorded in self.session_id_store.value (**non persistently**)

        .. note::
            Session ID is **saved persistently** to file: *self.session_id_store.file_path*

        Returns:
            **bool**: **True** if successful, otherwise **False**.
        """
        # try to read session_id from file
        self.session_id_store.value = self.session_id_store.read()

        if self.session_id_store.value:
            # got one.. check whether it's still valid
            try:
                if self.session_check_is_valid(self.session_id_store.value):
                    log.info("Using valid Session ID "
                             f"from ({self.session_id_store.file_path})")
                    return True
            except APIError:
                """Most likely invalid session_id. Remove it from session_id_store."""
                pass

        # got no (valid) session_id; clean store
        self.session_id_store.write("")

        # and try to create new one
        if not self.session_create():
            raise SessionCreateError("Failed to create a Session ID!")

        # save new created session_id to file
        if not self.session_id_store.write(self.result_json[self._session_key]):
            raise OSError("Failed to save Session ID to file!")
        else:
            log.info("Saved new Session ID to file: "
                     f"{self.session_id_store.file_path}")
            return True

    """
    GenericInterface::Operation::Ticket::TicketCreate
        * ticket_create
    """

    def ticket_create(self,
                      ticket=None,
                      article=None,
                      attachments=None,
                      dynamic_fields=None,
                      **kwargs):
        """Create a Ticket

        Args:
            ticket (Ticket): a ticket object
            article (Article): optional article
            attachments (list): *Attachment* objects
            dynamic_fields (list): *DynamicField* object
            **kwargs: any regular OTRS Fields (not for Dynamic Fields!)

        Returns:
            **dict** or **False**: dict if successful, otherwise **False**.
        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "TicketCreate"

        payload = {self._session_key: self.session_id_store.value}

        if not ticket:
            raise ArgumentMissingError("Ticket")

        if not article:
            raise ArgumentMissingError("Article")

        if isinstance(kwargs, dict) and len(kwargs) > 0:
            ticket.field_add(kwargs)

        payload.update(ticket.to_dct())

        if article:
            article.validate()
            payload.update({"Article": article.to_dct()})

        if attachments:
            # noinspection PyTypeChecker
            payload.update({"Attachment": [att.to_dct() for att in attachments]})

        if dynamic_fields:
            # noinspection PyTypeChecker
            payload.update({"DynamicField": [df.to_dct() for df in dynamic_fields]})

        if not self._parse_and_validate_response(self._send_request(payload)):
            return False
        else:
            return self.result_json

    """
    GenericInterface::Operation::Ticket::TicketGet

        * ticket_get_by_id
        * ticket_get_by_list
        * ticket_get_by_number
    """

    def ticket_get_by_id(self,
                         ticket_id,
                         articles=False,
                         attachments=False,
                         dynamic_fields=True,
                         html_body_as_attachment=False):
        """ticket_get_by_id

        Args:
            ticket_id (int): Integer value of a Ticket ID
            attachments (bool): will request OTRS to include attachments (*default: False*)
            articles (bool): will request OTRS to include all
                    Articles (*default: False*)
            dynamic_fields (bool): will request OTRS to include all
                    Dynamic Fields (*default: True*)
            html_body_as_attachment (bool): Optional, If enabled the HTML body version of
                    each article is added to the attachments list

        Returns:
            **Ticket** or **False**: Ticket object if successful, otherwise **False**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "TicketGet"

        payload = {
            self._session_key: self.session_id_store.value,
            "TicketID": f"{ticket_id}",
            "AllArticles": int(articles),
            "Attachments": int(attachments),
            "DynamicFields": int(dynamic_fields),
            "HTMLBodyAsAttachment": int(html_body_as_attachment),
        }

        response = self._send_request(payload, ticket_id)
        if not self._parse_and_validate_response(response):
            return False
        else:
            return self.result[0]

    def ticket_get_by_list(self,
                           ticket_id_list,
                           articles=False,
                           attachments=False,
                           dynamic_fields=True,
                           html_body_as_attachment=False):
        """ticket_get_by_list

        Args:
            ticket_id_list (list): List of either String or Integer values
            attachments (bool): will request OTRS to include attachments (*default: False*)
            articles (bool): will request OTRS to include all
                    Articles (*default: False*)
            dynamic_fields (bool): will request OTRS to include all
                    Dynamic Fields (*default: True*)
            html_body_as_attachment (bool): Optional, If enabled the HTML body version of
                    each article is added to the attachments list

        Returns:
            **list**: Ticket objects (as list) if successful, otherwise **False**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "TicketGetList"

        if not isinstance(ticket_id_list, list):
            raise ArgumentInvalidError("Please provide list of IDs!")

        # When you ask with an empty ticket_id_list, you get an empty response
        if not ticket_id_list:
            return []

        payload = {
            self._session_key: self.session_id_store.value,
            "TicketID": ','.join([str(item) for item in ticket_id_list]),
            "AllArticles": int(articles),
            "Attachments": int(attachments),
            "DynamicFields": int(dynamic_fields),
            "HTMLBodyAsAttachment": int(html_body_as_attachment),
        }

        if not self._parse_and_validate_response(self._send_request(payload)):
            return False
        else:
            return self.result

    def ticket_get_by_number(self,
                             ticket_number,
                             articles=False,
                             attachments=False,
                             dynamic_fields=True,
                             html_body_as_attachment=False):
        """ticket_get_by_number

        Args:
            ticket_number (str): Ticket Number as str
            attachments (bool): will request OTRS to include attachments (*default: False*)
            articles (bool): will request OTRS to include all
                    Articles (*default: False*)
            dynamic_fields (bool): will request OTRS to include all
                    Dynamic Fields (*default: True*)
            html_body_as_attachment (bool): Optional, If enabled the HTML body version of
                    each article is added to the attachments list

        Raises:
            ValueError

        Returns:
            **Ticket** or **False**: Ticket object if successful, otherwise **False**.

        """
        if isinstance(ticket_number, int):
            raise ArgumentInvalidError("Provide ticket_number as str/unicode. "
                                       "Got ticket_number as int.")
        result_list = self.ticket_search(TicketNumber=ticket_number)

        if not result_list:
            return False

        if len(result_list) == 1:
            result = self.ticket_get_by_id(result_list[0],
                                           articles=articles,
                                           attachments=attachments,
                                           dynamic_fields=dynamic_fields,
                                           html_body_as_attachment=html_body_as_attachment)
            if not result:
                return False
            else:
                return result
        else:
            # TODO 2016-11-12 (RH): more than one ticket found for a specific ticket number
            raise ValueError("Found more than one result for "
                             f"Ticket Number: {ticket_number}")

    """
    GenericInterface::Operation::Ticket::TicketHistoryGet

        * ticket_history_get_by_id
    """

    def ticket_history_get_by_id(self, ticket_id):
        """ticket_history_get_by_id

        Args:
            ticket_id (int): Integer value of a Ticket ID

        Returns:
            **dict** or **False**: A **dict** ("History") containing a list of dicts, otherwise **False**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "TicketHistoryGet"

        payload = {
            self._session_key: self.session_id_store.value,
            "TicketID": f"{ticket_id}"
        }

        response = self._send_request(payload, ticket_id)
        if not self._parse_and_validate_response(response):
            return False
        else:
            return self.result[0]

    """
    GenericInterface::Operation::Ticket::TicketSearch
        * ticket_search
        * ticket_search_full_text
    """

    def ticket_search(self, dynamic_fields=None, **kwargs):
        """Search for ticket

        Args:
            dynamic_fields (list): List of DynamicField objects for which the search
                should be performed
            **kwargs: Arbitrary keyword arguments (not for DynamicField objects).

        Returns:
            **list** or **False**: The search result (as list) if successful (can be an
                empty list: []), otherwise **False**.

        .. note::
            If value of kwargs is a datetime object then this object will be
            converted to the appropriate string format for OTRS API.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "TicketSearch"
        payload = {
            self._session_key: self.session_id_store.value,
        }

        if dynamic_fields:
            if isinstance(dynamic_fields, DynamicField):
                payload.update(dynamic_fields.to_dct_search())
            else:
                for df in dynamic_fields:
                    payload.update(df.to_dct_search())

        if kwargs is not None:
            for key, value in kwargs.items():
                if isinstance(value, datetime.datetime):
                    value = value.strftime("%Y-%m-%d %H:%M:%S")
                payload.update({key: value})

        if not self._parse_and_validate_response(self._send_request(payload)):
            return False
        else:
            return self.result

    def ticket_search_full_text(self, pattern):
        """Wrapper for search ticket for full text search

        Args:
            pattern (str): Search pattern (a '%' will be added to front and end automatically)

        Returns:
            **list** or **False**: The search result (as list) if successful,
                otherwise **False**.

        """
        self.operation = "TicketSearch"
        pattern_wildcard = f"%{pattern}%"

        if self.use_legacy_sessions:
            return self.ticket_search(FullTextIndex="1",
                                      ContentSearch="OR",
                                      Subject=pattern_wildcard,
                                      Body=pattern_wildcard)
        else:
            return self.ticket_search(FullTextIndex="1",
                                      ContentSearch="OR",
                                      MIMEBase_Subject=pattern_wildcard,
                                      MIMEBase_Body=pattern_wildcard)

    """
    GenericInterface::Operation::Ticket::TicketUpdate
        * ticket_update
        * ticket_update_set_pending
    """

    def ticket_update(self,
                      ticket_id,
                      article=None,
                      attachments=None,
                      dynamic_fields=None,
                      **kwargs):
        """Update a Ticket

        Args:

            ticket_id (int): Ticket ID as integer value
            article (Article): **optional** one *Article* that will be add to the ticket
            attachments (list): list of one or more *Attachment* objects that will
                be added to ticket. Also requires an *Article*!
            dynamic_fields (list): *DynamicField* objects
            **kwargs: any regular Ticket Fields (not for Dynamic Fields!)

        Returns:
            **dict** or **False**: A dict if successful, otherwise **False**.
        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "TicketUpdate"

        payload = {self._session_key: self.session_id_store.value, "TicketID": ticket_id}

        if article:
            article.validate()
            payload.update({"Article": article.to_dct()})

        if attachments:
            if not article:
                raise ArgumentMissingError("To create an attachment an article is needed!")
            # noinspection PyTypeChecker
            payload.update({"Attachment": [att.to_dct() for att in attachments]})

        if dynamic_fields:
            # noinspection PyTypeChecker
            payload.update({"DynamicField": [df.to_dct() for df in dynamic_fields]})

        if kwargs is not None and not kwargs == {}:
            ticket_dct = {}
            for key, value in kwargs.items():
                ticket_dct.update({key: value})
            payload.update({"Ticket": ticket_dct})

        if not self._parse_and_validate_response(self._send_request(payload, ticket_id)):
            return False

        return self.result_json

    def ticket_update_set_pending(self,
                                  ticket_id,
                                  new_state="pending reminder",
                                  pending_days=1,
                                  pending_hours=0):
        """ticket_update_set_state_pending

        Args:
            ticket_id (int): Ticket ID as integer value
            new_state (str): defaults to "pending reminder"
            pending_days (int): defaults to 1
            pending_hours (int): defaults to 0

        Returns:
            **dict** or **False**: A dict if successful, otherwise **False**.

        .. note::
            Operates in UTC
        """
        datetime_now = datetime.datetime.utcnow()
        pending_till = datetime_now + datetime.timedelta(days=pending_days, hours=pending_hours)

        pt = Ticket.datetime_to_pending_time_text(datetime_object=pending_till)

        return self.ticket_update(ticket_id, State=new_state, PendingTime=pt)

    """
    GenericInterface::Operation::Link::LinkAdd
        * link_add
    """

    def link_add(self,
                 src_object_id,
                 dst_object_id,
                 src_object_type="Ticket",
                 dst_object_type="Ticket",
                 link_type="Normal",
                 state="Valid"):
        """link_add

        Args:
            src_object_id (int): Integer value of source object ID
            dst_object_id (int): Integer value of destination object ID
            src_object_type (str): Object type of source; e.g. "Ticket", "FAQ"...
                (*default: Ticket*)
            dst_object_type (str): Object type of destination; e.g. "Ticket", "FAQ"...
                (*default: Ticket*)
            link_type (str): Type of the link: "Normal" or "ParentChild" (*default: Normal*)
            state (str): State of the link (*default: Normal*)

        Returns:
            **True** or **False**: True if successful, otherwise **False**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "LinkAdd"

        payload = {
            self._session_key: self.session_id_store.value,
            "SourceObject": src_object_type,
            "SourceKey": int(src_object_id),
            "TargetObject": dst_object_type,
            "TargetKey": int(dst_object_id),
            "Type": link_type,
            "State": state
        }

        return self._parse_and_validate_response(self._send_request(payload))

    """
    GenericInterface::Operation::Link::LinkDelete
        * link_delete
    """

    def link_delete(self,
                    src_object_id,
                    dst_object_id,
                    src_object_type="Ticket",
                    dst_object_type="Ticket",
                    link_type="Normal"):
        """link_delete

        Args:
            src_object_id (int): Integer value of source object ID
            src_object_type (str): Object type of source; e.g. "Ticket", "FAQ"...
                (*default: Ticket*)
            dst_object_id (int): Integer value of source object ID
            dst_object_type (str): Object type of source; e.g. "Ticket", "FAQ"...
                (*default: Ticket*)
            link_type (str): Type of the link: "Normal" or "ParentChild" (*default: Normal*)

        Returns:
            **True** or **False**: True if successful, otherwise **False**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "LinkDelete"

        payload = {
            self._session_key: self.session_id_store.value,
            "Object1": src_object_type,
            "Key1": int(src_object_id),
            "Object2": dst_object_type,
            "Key2": int(dst_object_id),
            "Type": link_type
        }

        return self._parse_and_validate_response(self._send_request(payload))

    """
    GenericInterface::Operation::Link::LinkDeleteAll
        * link_delete_all
    """

    def link_delete_all(self,
                        object_id,
                        object_type="Ticket"):
        """link_delete_all

        Args:
            object_id (int): Integer value of source object ID
            object_type (str): Object type of source; e.g. "Ticket", "FAQ"...
                (*default: Ticket*)

        Returns:
            **True** or **False**: True if successful, otherwise **False**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "LinkDeleteAll"

        payload = {
            self._session_key: self.session_id_store.value,
            "Object": object_type,
            "Key": int(object_id)
        }

        return self._parse_and_validate_response(self._send_request(payload))

    """
    GenericInterface::Operation::Link::LinkList
        * link_list
    """

    def link_list(self,
                  src_object_id,
                  src_object_type="Ticket",
                  dst_object_type=None,
                  state="Valid",
                  link_type=None,
                  direction=None):
        """link_list

        Args:
            src_object_id (int): Integer value of source object ID
            src_object_type (str): Object type of source; e.g. "Ticket", "FAQ"...
                (*default: Ticket*)
            dst_object_type (str): Object type of destination; e.g. "Ticket", "FAQ"...
                Optional restriction of the object where the links point to. (*default: Ticket*)
            state (str): State of the link (*default: Valid*)
            link_type (str): Type of the link: "Normal" or "ParentChild" (*default: Normal*)
            direction (str): Optional restriction of the link direction ('Source' or 'Target').

        Returns:
            **list** or **None**: List of found dict links if successful, if empty **None**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "LinkList"

        payload = {
            self._session_key: self.session_id_store.value,
            "Object": src_object_type,
            "Key": int(src_object_id),
            "State": state
        }

        if dst_object_type:
            payload.update({"Object2": dst_object_type})

        if link_type:
            payload.update({"Type": link_type})

        if direction:
            payload.update({"Direction": direction})

        result = None
        if self._parse_and_validate_response(self._send_request(payload)):
            result = self.result
        return result

    """
    GenericInterface::Operation::Link::PossibleLinkList
        * link_possible_link_list
    """

    def link_possible_link_list(self):
        """link_possible_link_list

        Returns:
            **List** or **False**: List if successful, otherwise **False**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "PossibleLinkList"

        payload = {
            self._session_key: self.session_id_store.value,
        }

        if self._parse_and_validate_response(self._send_request(payload)):
            return self.result
        else:
            return False

    """
    GenericInterface::Operation::Link::PossibleObjectsList
        * link_possible_objects_list
    """

    def link_possible_objects_list(self,
                                   object_type="Ticket"):
        """link_possible_objects_list

        Args:
            object_type (str): Object type; e.g. "Ticket", "FAQ"...
                (*default: Ticket*)

        Returns:
            **List** or **False**: List if successful, otherwise **False**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "PossibleObjectsList"

        payload = {
            self._session_key: self.session_id_store.value,
            "Object": object_type,
        }

        if self._parse_and_validate_response(self._send_request(payload)):
            return self.result
        else:
            return False

    """
    GenericInterface::Operation::Link::PossibleTypesList
        * link_possible_types_list
    """

    def link_possible_types_list(self,
                                 src_object_type="Ticket",
                                 dst_object_type="Ticket"):
        """link_possible_types_list

        Args:
            src_object_type (str): Object type of source; e.g. "Ticket", "FAQ"...
                (*default: Ticket*)
            dst_object_type (str): Object type of destination; e.g. "Ticket", "FAQ"...
                (*default: Ticket*)

        Returns:
            **List** or **False**: List if successful, otherwise **False**.

        """
        if not self.session_id_store.value:
            raise SessionNotCreated("Call session_create() or "
                                    "session_restore_or_create() first")
        self.operation = "PossibleTypesList"

        payload = {
            self._session_key: self.session_id_store.value,
            "Object1": src_object_type,
            "Object2": dst_object_type,
        }

        if self._parse_and_validate_response(self._send_request(payload)):
            return self.result
        else:
            return False

    def _build_url(self, data_id=None):
        """build url for request

        Args:
            data_id (optional[int])

        Returns:
            **str**: The complete URL where the request will be send to.

        """
        route = self.ws_config[self.operation]["Route"]

        if ":" in route:
            route_split = route.split(":")
            route = route_split[0]
            route_arg = route_split[1]

            if route_arg == "TicketID":
                if not data_id:
                    raise ValueError("TicketID is None but Route requires "
                                     f"TicketID: {route}")
                self._url = f"{self.baseurl}{self.webservice_path}{self.ws_ticket}{route}{data_id}"
            elif route_arg == "SessionID":
                if not data_id:
                    raise ValueError("SessionID is None but Route requires "
                                     f"SessionID: {route}")
                self._url = f"{self.baseurl}{self.webservice_path}{self.ws_ticket}{route}{data_id}"
        else:
            if route in self.routes_ticket:
                self._url = f"{self.baseurl}{self.webservice_path}{self.ws_ticket}{route}"
            elif route in self.routes_link:
                self._url = f"{self.baseurl}{self.webservice_path}{self.ws_link}{route}"

        return self._url

    def _send_request(self, payload=None, data_id=None):
        """send the API request using the *requests.request* method

        Args:
            payload (dict)
            data_id (optional[dict])

        Raises:
            OTRSHTTPError:

        Returns:
            **requests.Response**: Response received after sending the request.

        .. note::
            Supported HTTP Methods: DELETE, GET, HEAD, PATCH, POST, PUT
        """
        if not payload:
            raise ArgumentMissingError("payload")

        self._result_type = self.ws_config[self.operation]["Result"]

        url = self._build_url(data_id)

        http_method = self.ws_config[self.operation]["RequestMethod"]

        if http_method not in ["DELETE", "GET", "HEAD", "PATCH", "POST", "PUT"]:
            raise ValueError("invalid http_method")

        headers = {}

        if self.user_agent:
            headers.update({"User-Agent": self.user_agent})

        if http_method == "GET":

            # print("sending {0} to {1} as {2}".format(payload, url, http_method.upper()))
            try:
                response = requests.request("GET",
                                            url,
                                            headers=headers,
                                            params=payload,
                                            proxies=self.proxies,
                                            verify=self.https_verify,
                                            cert=self.client_auth_cert,
                                            auth=self.auth,
                                            timeout=self.request_timeout)

                # store a copy of the request
                self._request = response.request

            # critical error: HTTP request resulted in an error!
            except Exception as err:
                # raise OTRSHTTPError("get http")
                raise HTTPError("Failed to access OTRS. Check Hostname, Proxy, SSL Certificate!\n"
                                f"Error with http communication: {err}")

        else:

            headers.update({"Content-Type": "application/json"})

            json_payload = json.dumps(payload)

            # print("sending {0} to {1} as {2}".format(payload, url, http_method.upper()))
            try:
                response = requests.request(http_method.upper(),
                                            url,
                                            headers=headers,
                                            data=json_payload,
                                            proxies=self.proxies,
                                            verify=self.https_verify,
                                            cert=self.client_auth_cert,
                                            auth=self.auth,
                                            timeout=self.request_timeout)

                # store a copy of the request
                self._request = response.request

            # critical error: HTTP request resulted in an error!
            except Exception as err:
                # raise OTRSHTTPError("get http")
                raise HTTPError("Failed to access OTRS. Check Hostname, Proxy, SSL Certificate!\n"
                                f"Error with http communication: {err}")

        if not response.status_code == 200:
            raise HTTPError("Received HTTP Error. Check Hostname and WebServiceName.\n"
                            f"HTTP Status Code: {response.status_code}\n"
                            f"HTTP Message: {response.content}")
        return response

    def _parse_and_validate_response(self, response):
        """_parse_and_validate_response

        Args:
            response (requests.Response): result of _send_request

        Raises:
            OTRSAPIError
            NotImplementedError
            ResponseParseError

        Returns:
            **bool**: **True** if successful

        """

        if not isinstance(response, requests.models.Response):
            raise ValueError("requests.Response object expected!")

        if self.operation not in self.ws_config.keys():
            raise ValueError("invalid operation")

        # clear data from Client
        self.result = None
        self._result_error = False

        # get and set new data
        self.result_json = response.json()
        self._result_status_code = response.status_code
        self._result_content = response.content

        # handle TicketSearch operation first. special: empty search result has no "TicketID"
        if self.operation == "TicketSearch":
            if not self.result_json:
                self.result = []
                return True
            if self.result_json.get(self._result_type, None):
                self.result = self.result_json['TicketID']
                return True

        # now handle SessionGet operation
        if self.operation in ["SessionGet"]:
            # For SessionGet the "Result" that is returned is different when legacy session
            # are used.
            # SessionData was default in OTRS <= 7 / PyOTRS used it as default from v0.1.
            # AccessTokenData was introduced in OTRS 8 - for CustomerUser already in 7 (?!).
            # Unless the dict was modified - use the hardcoded defaults accordingly.
            if self._result_type not in ["AccessTokenData", "SessionData"]:
                session_result_type = self._result_type
            else:
                if self.use_legacy_sessions:
                    session_result_type = "SessionData"
                else:
                    session_result_type = "AccessTokenData"

            _session_data = self.result_json.get(session_result_type, None)
            if _session_data:  # received SessionData -> Session ID is valid
                self._result_error = False
                self.result = self.result_json[session_result_type]
                return True
            elif self.result_json["Error"]["ErrorCode"] == "SessionGet.SessionInvalid":
                return False
            else:
                raise APIError("Failed to access OTRS API.\n"
                               "OTRS Error Code: {}\nOTRS Error Message: {}"
                               "".format(self.result_json["Error"]["ErrorCode"],
                                         self.result_json["Error"]["ErrorMessage"]))

        # handle Link operations; Add, Delete, DeleteAll return: {"Success":1}
        if self.operation in ["LinkAdd", "LinkDelete", "LinkDeleteAll"]:
            if self.result_json.get("Success", None) == 1:
                return True

        # LinkList result can be empty
        if self.operation in "LinkList":
            _link_list = self.result_json.get("LinkList", None)
            if not _link_list:
                self.result = None
                return True
            else:
                self.result = _link_list
                return True

        # now handle other operations
        if self.result_json.get(self._result_type, None):
            self._result_error = False
            self.result = self.result_json[self._result_type]
        elif self.result_json.get("Error", None):
            self._result_error = True
        else:
            self._result_error = True
            # critical error: Unknown response from OTRS API - FAIL NOW!
            raise ResponseParseError("Unknown key in response JSON DICT!")

        # report error
        if self._result_error:
            raise APIError("Failed to access OTRS API. Check Username and Password! "
                           "Session ID expired?! Does Ticket exist?\n"
                           "OTRS Error Code: {}\nOTRS Error Message: {}"
                           "".format(self.result_json["Error"]["ErrorCode"],
                                     self.result_json["Error"]["ErrorMessage"]))

        # for operation TicketGet: parse result list into Ticket object list
        if self.operation == "TicketGet" or self.operation == "TicketGetList":
            self.result = [Ticket(item) for item in self.result_json['Ticket']]

        return True

# EOF
