# coding: utf-8
#
# Copyright 2010 Alexandre Fiori
# based on the original Tornado by Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Support for sending e-mails with attachments to SMTP servers over
plain text, SSL or TLS.

For more information, check out the `e-mail demo
<https://github.com/fiorix/cyclone/tree/master/demos/email>`_.
"""

import types
import os.path

from cStringIO import StringIO
from OpenSSL.SSL import SSLv3_METHOD

from email import Encoders
from email.MIMEText import MIMEText
from email.MIMEBase import MIMEBase
from email.MIMEMultipart import MIMEMultipart
from email.Utils import COMMASPACE, formatdate

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.ssl import ClientContextFactory
from twisted.mail.smtp import ESMTPSenderFactory, quoteaddr


class Message(object):
    """Create new e-mail messages.

    Example::

        msg = mail.Message(
                from_addr="root@localhost",
                to_addrs=["user1", "user2", "user3"],
                subject="Test, 123",
                message="Hello thar!",
                mime="text/html")
    """

    def __init__(self, from_addr, to_addrs, subject, message,
                 mime="text/plain", charset="utf-8"):
        self.subject = subject
        self.from_addr = from_addr

        if isinstance(to_addrs, types.StringType):
            self.to_addrs = [to_addrs]
        else:
            self.to_addrs = to_addrs

        self.msg = None
        self.__cache = None
        self.message = MIMEText(message, _charset=charset)
        self.message.set_type(mime)

    def attach(self, filename, mime=None, charset=None, content=None):
        """Attach files to this message.

        Example::

            msg.attach("me.png", mime="image/png")

        It also supports fake attachments::

            msg.attach("fake.txt", mime="text/plain", content="gotcha")
        """
        base = os.path.basename(filename)
        if content is None:
            fd = open(filename)
            content = fd.read()
            fd.close()
        elif not isinstance(content, types.StringType):
            raise TypeError("Don't know how to attach content: %s" %
                            repr(content))

        part = MIMEBase("application", "octet-stream")
        part.set_payload(content)
        Encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        "attachment", filename=base)

        if mime is not None:
            part.set_type(mime)

        if charset is not None:
            part.set_charset(charset)

        if self.msg is None:
            self.msg = MIMEMultipart()
            self.msg.attach(self.message)

        self.msg.attach(part)

    def __str__(self):
        return self.__cache or "cyclone email message: not rendered yet"

    def render(self):
        if self.msg is None:
            self.msg = self.message

        self.msg["Subject"] = self.subject
        self.msg["From"] = self.from_addr
        self.msg["To"] = COMMASPACE.join(self.to_addrs)
        self.msg["Date"] = formatdate(localtime=True)

        if self.__cache is None:
            self.__cache = self.msg.as_string()

        return StringIO(self.__cache)

    def add_header(self, key, value, **params):
        """Adds custom headers to this message.

        Example::

            msg.add_header("X-MailTag", "foobar")
        """
        if self.msg is None:
            self.msg = self.message

        self.msg.add_header(key, value, **params)


def sendmail(mailconf, message):
    """Takes a regular dictionary as mailconf, as follows.

    Example::

        mailconf = dict(
            host="smtp.gmail.com",  # required
            port=25,                # optional, default 25 or 587 for SSL/TLS
            username=foo,           # optional, no default
            password=bar,           # optional, no default
            tls=True,               # optional, default False
        )

        d = mail.sendmail(mailconf, msg)
        d.addCallback(on_response)
    """
    if not isinstance(mailconf, types.DictType):
        raise TypeError("mailconf must be a regular python dictionary")

    if not isinstance(message, Message):
        raise TypeError("message must be an instance of cyclone.mail.Message")

    host = mailconf.get("host")

    if isinstance(host, unicode):
        host = str(unicode)

    if not isinstance(host, types.StringType):
        raise ValueError("mailconf requires a 'host' configuration")

    use_tls = mailconf.get("tls")

    if use_tls:
        port = mailconf.get("port", 587)
        contextFactory = ClientContextFactory()
        contextFactory.method = SSLv3_METHOD
    else:
        port = mailconf.get("port", 25)
        contextFactory = None

    if not isinstance(port, types.IntType):
        raise ValueError("mailconf requires a proper 'port' configuration")

    result = Deferred()
    u = mailconf.get("username")
    p = mailconf.get("password")
    factory = ESMTPSenderFactory(u, p,
                                 quoteaddr(message.from_addr),
                                 message.to_addrs,
                                 message.render(),
                                 result,
                                 contextFactory=contextFactory,
                                 requireAuthentication=(u and p),
                                 requireTransportSecurity=use_tls)

    reactor.connectTCP(host, port, factory)
    return result
