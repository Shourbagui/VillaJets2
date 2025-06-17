import os
import email
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from imapclient import IMAPClient
from crm.models import Mail, Client

class Command(BaseCommand):
    help = 'Fetch Gmail inbox emails from the last month and store them as Mail objects.'

    def handle(self, *args, **options):
        mail_user = settings.MAIL_USER or os.getenv('MAIL_USER')
        mail_password = settings.MAIL_PASSWORD or os.getenv('MAIL_PASSWORD')
        if not mail_user or not mail_password:
            self.stderr.write(self.style.ERROR('MAIL_USER and MAIL_PASSWORD must be set in .env or settings.py'))
            return

        server = IMAPClient('imap.gmail.com', ssl=True)
        try:
            server.login(mail_user, mail_password)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Login failed: {e}'))
            return

        server.select_folder('INBOX')
        since_date = (datetime.now() - timedelta(days=30)).date()
        messages = server.search(['SINCE', since_date.strftime('%d-%b-%Y')])
        self.stdout.write(f'Found {len(messages)} messages since {since_date}')

        for uid, message_data in server.fetch(messages, ['RFC822']).items():
            msg = email.message_from_bytes(message_data[b'RFC822'])
            subject = email.header.decode_header(msg.get('Subject'))[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode(errors='ignore')
            from_ = email.utils.parseaddr(msg.get('From'))
            sender_name = from_[0] or from_[1]
            email_addr = from_[1]
            # Get email body (plain text preferred)
            body = ''
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain' and part.get_content_disposition() != 'attachment':
                        charset = part.get_content_charset() or 'utf-8'
                        body = part.get_payload(decode=True).decode(charset, errors='ignore')
                        break
            else:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset, errors='ignore')
            # Store in DB if not already present (by subject and sender email)
            if not Mail.objects.filter(subject=subject, email=email_addr).exists():
                # Try to link to a client
                client = None
                try:
                    client = Client.objects.get(email=email_addr)
                except Client.DoesNotExist:
                    pass # No client found with this email

                Mail.objects.create(
                    client=client,
                    sender=sender_name,
                    email=email_addr,
                    subject=subject,
                    content=body,
                    is_read=False
                )
        server.logout()
        self.stdout.write(self.style.SUCCESS('Fetched and stored emails successfully.')) 