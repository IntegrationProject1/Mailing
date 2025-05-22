import pika, json, os
import logging
import threading
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import xml.etree.ElementTree as ET
from lxml import etree
from io import StringIO, BytesIO
import qrcode
import base64
import requests
from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition, ContentId
import tempfile

_logger = logging.getLogger(__name__)

# Configuration settings
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST')
RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT'))
RABBITMQ_USER = os.environ.get('RABBITMQ_USER')
RABBITMQ_PASSWORD = os.environ.get('RABBITMQ_PASSWORD')
SERVICE_TEMPLATES = {
    'qrcode':     os.environ['QRCODE_TEMPLATE_ID'],
    'facturatie':  os.environ['FACTURATIE_TEMPLATE_ID'],
    'controlroom': os.environ['CONTROLROOM_TEMPLATE_ID'],
    'frontend':    os.environ['FRONTEND_TEMPLATE_ID'],
}
QUEUE_NAME = 'mail_queue_test'


# XSD schema definiëren
XSD_SCHEMA = '''<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:element name="emailMessage">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="to"   type="xs:string"/>
        <xs:element name="from" type="xs:string"/>
        <xs:element name="subject" type="xs:string"/>
        <xs:element name="title" type="xs:string"/>
        <xs:element name="opener" type="xs:string"/>
        <xs:element name="body" type="xs:string"/>
        <xs:element name="footer" type="xs:string"/>
        <xs:element name="attachmenturl" type="xs:string" minOccurs="0"/>
      </xs:sequence>
      <!-- Nieuw attribuut: naam van de service -->
      <xs:attribute name="service" type="xs:string" use="required"/>
    </xs:complexType>
  </xs:element>

</xs:schema>
'''

def log_message(message):
    print(f"[MAILING] {message}")
    _logger.info(message)

log_message("Starting mail service...")

# Schema parsen en valideren
schema_root = etree.parse(BytesIO(XSD_SCHEMA.encode('utf-8')))
schema = etree.XMLSchema(schema_root)
    
def validate_xml(xml_string):
    """Valideert XML input tegen het XSD schema"""
    log_message("Validating XML message")
    try:
        xml_doc = etree.parse(BytesIO(xml_string.encode('utf-8')))
        schema.assertValid(xml_doc)
        log_message("XML validation successful")
        return True, xml_doc
    except etree.XMLSyntaxError as e:
        error_msg = f"XML parsing error: {str(e)}"
        log_message(error_msg)
        return False, error_msg
    except etree.DocumentInvalid as e:
        error_msg = f"XML validation error: {str(e)}"
        log_message(error_msg)
        return False, error_msg

def xml_to_dict(xml_doc):
    log_message("Converting XML to dictionary")
    root = xml_doc.getroot()

    service = root.get('service')
    if not service or service not in SERVICE_TEMPLATES:
        raise ValueError(f"Onbekende of ontbrekende service: {service!r}")
    template_id = SERVICE_TEMPLATES[service.lower()] # if they write it with a capital letter

    # Velden die verplicht aanwezig moeten zijn
    required_fields = ['to', 'from', 'subject']
    for field in required_fields:
        value = root.findtext(field)
        if not value or not value.strip():
            raise ValueError(f"Verplicht veld '{field}' is leeg of ontbreekt.")

    try:
        data = {
            'service': service,
            'template_id': template_id,
            'to':      root.findtext('to'),
            'from':    root.findtext('from'),
            'subject': root.findtext('subject'),
            'dynamic_template_data': {
                'subject': root.findtext('subject'),
                'title':  root.findtext('title'),
                'opener': root.findtext('opener'),
                'body':   root.findtext('body'),
                'footer': root.findtext('footer'),
            }
        }
        attachment_url = root.findtext("attachmenturl")
        if attachment_url:
            data["attachment_url"] = attachment_url

        log_message(
          f"XML converted successfully. Service: {service}, "
          f"Recipient: {data['to']}, Subject: {data['subject']}, "
          f"Template: {template_id}"
        )
        return data

    except Exception as e:
        log_message(f"Error converting XML to dict: {str(e)}")
        raise

def download_file(url, save_path):
    """Downloads a file from the given URL and saves it to the specified path."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        log_message(f"File downloaded successfully from {url} to {save_path}")
        return save_path
    except Exception as e:
        log_message(f"Error downloading file from {url}: {str(e)}")
        raise

def send_email(data):
    log_message(f"Sending email for service '{data['service']}' "
                f"to {data['to']} with subject '{data['subject']}'")
    try:
        message = Mail(
            from_email=data['from'],
            to_emails=data['to'],
        )

        message.template_id = data['template_id']
        message.dynamic_template_data = data['dynamic_template_data']

        # Only generate QR code if the service is 'qrcode'
        if data['service'] == 'qrcode':
            qr_content = data['dynamic_template_data']['body']

            # Generate QR code image in memory
            qr = qrcode.make(qr_content)
            buffered = BytesIO()
            qr.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # Create embedded image attachment (CID = qrimage)
            attachment = Attachment(
                FileContent(qr_base64),
                FileName("qrcode.png"),
                FileType("image/png"),
                Disposition("inline"),
                ContentId("qrimage")
            )
            message.add_attachment(attachment)

        # Handle optional attachment from URL only for "facturatie" service
        if data['service'] == 'facturatie':
            attachment_url = data.get('attachment_url')
            temp_file_path = None
            if attachment_url:
                try:
                    # Download the file to a temporary location
                    temp_dir = tempfile.gettempdir()
                    temp_file_path = os.path.join(temp_dir, "attachment.pdf")
                    download_file(attachment_url, temp_file_path)

                    # Read and encode the file for SendGrid
                    with open(temp_file_path, 'rb') as f:
                        file_data = f.read()
                        encoded_file = base64.b64encode(file_data).decode()

                    # Attach the file to the email
                    attachment = Attachment(
                        FileContent(encoded_file),
                        FileName(os.path.basename(temp_file_path)),
                        FileType('application/pdf'),
                        Disposition('attachment')
                    )
                    message.add_attachment(attachment)
                except Exception as e:
                    log_message(f"Failed to download or attach file from {attachment_url}: {e}")
                    raise
                finally:
                    # Delete the temporary file after sending
                    if temp_file_path and os.path.exists(temp_file_path):
                        try:
                            os.remove(temp_file_path)
                            log_message(f"Temporary file {temp_file_path} deleted after sending.")
                        except Exception as e:
                            log_message(f"Failed to delete temporary file {temp_file_path}: {e}")

        # Send the email using SendGrid
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        log_message(f"Email sent successfully. Status code: {response.status_code}")

    except Exception as e:
        log_message(f"Error sending templated email: {str(e)}")
        raise




def callback(ch, method, properties, body):
    # Controleer of het bericht JSON of XML is
    message_id = method.delivery_tag
    content_type = properties.content_type if properties.content_type else 'NONE'
    message_text = body.decode('utf-8')
    log_message(f"Received message #{message_id} with content-type: {content_type}")
    
    # kijken of het een XML bericht is
    is_xml = message_text.strip().startswith('<?xml') or '<emailMessage>' in message_text
    
    try:
        if is_xml or ('xml' in content_type.lower()):
            log_message(f"Processing as XML message #{message_id}")
            # XML bericht verwerken
            is_valid, result = validate_xml(message_text)
            if is_valid:
                data = xml_to_dict(result)
                send_email(data)
                ch.basic_ack(delivery_tag=method.delivery_tag)
                log_message(f"XML message #{message_id} processed successfully")
            else:
                log_message(f"Invalid XML message #{message_id}: {result}")
                # Bericht afwijzen (reject) of naar dead-letter queue sturen
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                log_message(f"Message #{message_id} rejected")
        else:
            # Try to process as JSON
            log_message(f"Processing as JSON message #{message_id}")
            try:
                data = json.loads(message_text)
                send_email(data)
                ch.basic_ack(delivery_tag=method.delivery_tag)
                log_message(f"JSON message #{message_id} processed successfully")
            except json.JSONDecodeError as e:
                log_message(f"Invalid JSON format: {str(e)}")
                log_message(f"Message content: {message_text[:100]}...")  # Log first 100 chars
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                log_message(f"Message #{message_id} rejected due to invalid format")
    except Exception as e:
        log_message(f"Error processing message #{message_id}: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        log_message(f"Message #{message_id} rejected due to error")

class MailService:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.max_retries = 5
        self.retry_interval = 5
        
    def connect(self):
        """Connect to RabbitMQ with retry logic"""
        for retry in range(self.max_retries):
            try:
                log_message("Initializing RabbitMQ connection")
                credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
                params = pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=credentials,
                )

                self.connection = pika.BlockingConnection(params)
                self.channel = self.connection.channel()

                log_message("Connected to RabbitMQ successfully")

                # Declare exchange
                exchange_name = 'email'
                self.channel.exchange_declare(exchange='email', exchange_type='topic', durable=True)
                log_message(f"Exchange '{exchange_name}' declared")

                # Declare queue
                self.channel.queue_declare(queue=QUEUE_NAME, durable=True)
                log_message(f"Queue '{QUEUE_NAME}' declared")

                # Bind queue to exchange
                routing_key = 'mail'
                self.channel.queue_bind(exchange=exchange_name, queue=QUEUE_NAME, routing_key=routing_key)
                log_message(f"Queue '{QUEUE_NAME}' bound to exchange '{exchange_name}' with routing key '{routing_key}'")

                return True

            except Exception as e:
                log_message(f"Connection attempt {retry+1} failed: {str(e)}")
                time.sleep(self.retry_interval)
        return False

        
    def run(self):
        """Main method to start the mail service"""
        if not self.connect():
            log_message("Failed to connect to RabbitMQ. Service will exit.")
            return
            
        try:
            self.channel.queue_declare(queue=QUEUE_NAME, durable=True)
            log_message(f"Queue '{QUEUE_NAME}' declared")
            
            self.channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
            log_message(f"Starting to consume messages from queue '{QUEUE_NAME}'")
            
            # Start consuming messages - this is a blocking call
            self.channel.start_consuming()
            
        except Exception as e:
            log_message(f"Unexpected error: {str(e)}")
            import traceback
            log_message(f"Stack trace: {traceback.format_exc()}")
            self.shutdown()
            
    def shutdown(self):
        """Close connection and perform cleanup"""
        log_message("Shutting down mail service")
        if self.connection and self.connection.is_open:
            self.connection.close()
            log_message("RabbitMQ connection closed")

# Main execution block - this is what was missing
if __name__ == "__main__":
    log_message("Mail service application starting")
    
    # Log configuration
    log_message(f"Using RabbitMQ config: {RABBITMQ_HOST}:{RABBITMQ_PORT}, user: {RABBITMQ_USER}")
    log_message(f"Sendgrid API Key: {'Configured' if SENDGRID_API_KEY else 'Not configured'}")
    
    # Start the service
    service = MailService()
    service.run()
    
    log_message("Mail service application ended")


# test data om op de queue te zetten
'''
<?xml version="1.0" encoding="UTF-8"?>
<emailMessage service="facturatie">
  <to>reply.expomail@gmail.com</to>
  <from>no.reply.expomail@gmail.com</from>
  <subject>Uw factuur is klaar</subject>
  <title>Factuur #12345</title>
  <opener>Beste Jan,</opener>
  <body>Uw factuur van mei vindt u als bijlage.</body>
  <footer>Met vriendelijke groet, Finance Dept.</footer>
  <attachmenturl>http://integrationproject-2425s2-001.westeurope.cloudapp.azure.com:30081/invoice/pdf/89db4542eca7be0ba9e961c5a7ddbbada12e48944e752e0abd6878dc2f2af13f7a95a3a0b5a068a3de8f342b9038d544968011f9d090883eafb5dbef53d9fb58bba9e8470f494871a249992d88228c98a3f0827fa27bfbdf4536eda8884a46d9bccdc6fc11ca7f5a5d1834d337b85ff316fb8b1a7b</attachmenturl>
</emailMessage>
'''

'''
<?xml version="1.0" encoding="UTF-8"?>
<emailMessage service="frontend">
  <to>reply.expomail@gmail.com</to>
  <from>no.reply.expomail@gmail.com</from>
  <subject>qrcode Milan</subject>
  <title></title>
  <opener>Beste Milan,</opener>
  <body>Hier kunt u uw qrcode vinden</body>
  <footer>Met vriendelijke groet, Expo.</footer>
</emailMessage>
'''


