import pika, json, os
import logging
import threading
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import xml.etree.ElementTree as ET
from lxml import etree
from io import StringIO, BytesIO

_logger = logging.getLogger(__name__)

# Configuration settings
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST')
RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT'))
RABBITMQ_USER = os.environ.get('RABBITMQ_USER')
RABBITMQ_PASSWORD = os.environ.get('RABBITMQ_PASSWORD')
TEMPLATE_ID = os.environ.get('TEMPLATE_ID')
QUEUE_NAME = 'mail_queue'

# XSD schema definiëren
XSD_SCHEMA = '''<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="emailMessage">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="to" type="xs:string"/>
        <xs:element name="subject" type="xs:string"/>
        <xs:element name="htmlcontent" type="xs:string"/>
      </xs:sequence>
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
    """Converteert XML naar dictionary format voor de email service"""
    log_message("Converting XML to dictionary")
    root = xml_doc.getroot()
    try:
        data = {
            'to': root.find('to').text,
            'subject': root.find('subject').text,
            'htmlcontent': root.find('htmlcontent').text 
        }
        log_message(f"XML converted successfully. Recipient: {data['to']}, Subject: {data['subject']}")
        return data
    except Exception as e:
        log_message(f"Error converting XML to dict: {str(e)}")
        raise

def send_email(data):
    log_message(f"Sending email to {data['to']} with subject '{data['subject']}'")
    try:
        message = Mail(
            from_email= SENDGRID_API_KEY,
            to_emails=data['to'],
            template_id= TEMPLATE_ID,
            dynamic_template_data={
                'subject': data['subject'],
                'body': data[''] # add extra fields here if needed
            }
        )
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        log_message(f"Email sent successfully. Status code: {response.status_code}")
    except Exception as e:
        log_message(f"Error sending email: {str(e)}")
        raise

def callback(ch, method, properties, body):
    # Controleer of het bericht JSON of XML is
    message_id = method.delivery_tag
    content_type = properties.content_type if properties.content_type else 'NONE'
    message_text = body.decode('utf-8')
    log_message(f"Received message #{message_id} with content-type: {content_type}")
    
    # Check if content looks like XML regardless of content-type
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
                return True
                
            except Exception as e:
                log_message(f"Connection attempt {retry+1} failed: {str(e)}")        
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






# <?xml version="1.0" encoding="UTF-8"?>
# <emailMessage>
#     <to>test@example.com</to>
#     <subject>Test Email from Mail Service</subject>
#     <htmlcontent>
#         <![CDATA[
#         <html>
#             <body>
#                 <h1>This is a test email</h1>
#                 <p>Hello! This is a test message sent to verify that the mail service is working correctly.</p>
#                 <p>The time of sending was: 2025-05-01 12:00:00</p>
#                 <hr/>
#                 <p>If you received this email, the mail service is functioning properly.</p>
#             </body>
#         </html>
#         ]]>
#     </htmlcontent>
# </emailMessage>