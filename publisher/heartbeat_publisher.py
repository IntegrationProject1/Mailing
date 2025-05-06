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
    
    
