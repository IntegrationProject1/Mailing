import pytest
from unittest.mock import patch, MagicMock, mock_open, patch
from mail_service import validate_xml, xml_to_dict, send_email, callback


# Geldig XML bericht
VALID_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<emailMessage service="facturatie">
  <to>test@example.com</to>
  <from>from@example.com</from>
  <subject>Test</subject>
  <title>Hello</title>
  <opener>Beste klant</opener>
  <body>Inhoud</body>
  <footer>Groet</footer>
  <attachmenturl>http://example.com/invoice.pdf</attachmenturl>
</emailMessage>'''

INVALID_XML = '''<emailMessage><to></to></emailMessage>'''  # Onvolledig

# geldig XML bericht
@patch.dict("mail_service.SERVICE_TEMPLATES", {"facturatie": "dummy"})
def test_validate_xml_valid():
    valid, result = validate_xml(VALID_XML)
    assert valid is True
    assert result is not None
# ongeldig XML bericht
def test_validate_xml_invalid():
    valid, result = validate_xml(INVALID_XML)
    assert not valid
    assert "error" in result.lower()

# Testen van de xml_to_dict functie
@patch.dict("mail_service.SERVICE_TEMPLATES", {"facturatie": "dummy"})
def test_xml_to_dict_valid():
    valid, xml_doc = validate_xml(VALID_XML)
    assert valid
    data = xml_to_dict(xml_doc)
    assert data['to'] == 'test@example.com'
    assert data['service'] == 'facturatie'
    assert data['template_id'] == 'dummy'
    assert 'attachment_url' in data


@patch("builtins.open", new_callable=mock_open, read_data=b"fake-pdf-data")
@patch("mail_service.SendGridAPIClient")
@patch.dict("mail_service.SERVICE_TEMPLATES", {"facturatie": "dummy"})
@patch("mail_service.download_file")
def test_send_email_success(mock_download_file, mock_sendgrid_client, mock_open_file):
    ...

    mock_download_file.return_value = "/tmp/fakefile.pdf"

    # Fake SendGrid client antwoord
    mock_client_instance = MagicMock()
    mock_client_instance.send.return_value.status_code = 202
    mock_sendgrid_client.return_value = mock_client_instance

    data = {
        'from': 'from@example.com',
        'to': 'to@example.com',
        'subject': 'Test Subject',
        'service': 'facturatie',
        'template_id': 'dummy',
        'dynamic_template_data': {
            'subject': 'Test Subject',
            'title': 'Title',
            'opener': 'Beste',
            'body': 'Inhoud',
            'footer': 'Groet'
        },
        'attachment_url': 'http://example.com/invoice.pdf'
    }

    send_email(data)
    mock_sendgrid_client.return_value.send.assert_called_once()


@patch("mail_service.send_email")
def test_callback_json_valid(mock_send_email):
    mock_ch = MagicMock()
    mock_method = MagicMock(delivery_tag=1)
    mock_properties = MagicMock(content_type="application/json")

    json_body = b'''{
        "from": "from@example.com",
        "to": "to@example.com",
        "subject": "Test Subject",
        "service": "facturatie",
        "template_id": "dummy",
        "dynamic_template_data": {
            "subject": "Test",
            "title": "Hi",
            "opener": "Beste",
            "body": "Test",
            "footer": "Groet"
        }
    }'''

    callback(mock_ch, mock_method, mock_properties, json_body)
    mock_send_email.assert_called_once()
    mock_ch.basic_ack.assert_called_once_with(delivery_tag=1)


@patch("mail_service.send_email")
@patch.dict("mail_service.SERVICE_TEMPLATES", {"facturatie": "dummy"})
def test_callback_xml_valid(mock_send_email):
    mock_ch = MagicMock()
    mock_method = MagicMock(delivery_tag=1)
    mock_props = MagicMock(content_type="application/xml")

    callback(mock_ch, mock_method, mock_props, VALID_XML.encode("utf-8"))
    mock_send_email.assert_called_once()
    mock_ch.basic_ack.assert_called_once_with(delivery_tag=1)
