import os
import time
import pika
from lxml import etree

# Generate heartbeat XML from service name
def generate_heartbeat_xml(service_name):
    return f"""
    <Heartbeat>
        <ServiceName>{service_name}</ServiceName>
    </Heartbeat>
    """.strip()
    
# Validate heartbeat XML against XSD
def validate_heartbeat_xml(xml_str, xsd_path=None):
    if not xsd_path:
        current_dir = os.path.dirname(__file__)
        xsd_path = os.path.join(current_dir, "heartbeat.xsd")

    try:
        xml_doc = etree.fromstring(xml_str.encode("utf-8"))
        with open(xsd_path, 'rb') as f:
            xmlschema_doc = etree.parse(f)
            xmlschema = etree.XMLSchema(xmlschema_doc)
        xmlschema.assertValid(xml_doc)
        return True, None
    except etree.DocumentInvalid as e:
        return False, str(e)
    except Exception as e:
        return False, f"Validation error: {e}"

# Send heartbeat XML to RabbitMQ  
def send_heartbeat_periodically(service_name, queue_name="controlroom.heartbeat.ping", interval=1):
    time.sleep(10)  # Wait for RabbitMQ to be ready

    credentials = pika.PlainCredentials(
        os.getenv("RABBITMQ_USER", "guest"),
        os.getenv("RABBITMQ_PASSWORD", "guest")
    )
    parameters = pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", 5672)),
        credentials=credentials
    )

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    exchange_name = "heartbeat_monitoring"
    
    channel.exchange_declare(exchange=exchange_name, exchange_type="direct", durable=True)
    channel.queue_declare(queue=queue_name, durable=True)
    channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

    while True:
        heartbeat_xml = generate_heartbeat_xml(service_name)
        valid, error = validate_heartbeat_xml(heartbeat_xml)

        if not valid:
            print(f"Invalid XML: {error}")
        else:
            channel.basic_publish(
                exchange=exchange_name,
                routing_key=queue_name,
                body=heartbeat_xml,
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"Heartbeat sent: {heartbeat_xml}")

        time.sleep(interval)

    connection.close()

# Main function to run the heartbeat publisher
if __name__ == "__main__":
    service_name = os.getenv("SERVICE_NAME", "MailingService")
    send_heartbeat_periodically(service_name)