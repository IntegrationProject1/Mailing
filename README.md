# Mailing Service

## How to Use

### Prerequisites
1. Download and install the required software (e.g., Docker, RabbitMQ, etc.).
2. Ensure you have access to the RabbitMQ Dashboard and SendGrid API.

### Setup Instructions
1. **Clone the Repository**  
    Clone the GitHub repository to your working directory:  
    ```bash
    git clone https://github.com/IntegrationProject1/Mailing.git
    cd Mailing
    ```

2. **Configure Environment Variables**  
    Create a `.env` file in the root of the project and add the following keys with your configuration:
    ```env
    RABBITMQ_HOST=
    RABBITMQ_PORT=
    RABBITMQ_USER=
    RABBITMQ_PASSWORD=

    SENDGRID_API_KEY=

    QRCODE_TEMPLATE_ID=
    FACTURATIE_TEMPLATE_ID=
    CONTROLROOM_TEMPLATE_ID=
    FRONTEND_TEMPLATE_ID=
    ```

3. **Set Up RabbitMQ**  
    - In your RabbitMQ Dashboard, create an exchange named `email`.
    - Add a queue named `mail_queue`.

4. **Run the Application**  
    Use Docker Compose to build and start the service:
    ```bash
    docker compose down && docker compose up --build -d
    ```

    The `mail_service` should start and begin consuming messages from the RabbitMQ queue.

### Stopping the Service
To stop the container, use the following command:
```bash
docker container stop <container-name>
```

## Notes
- Ensure all environment variables are correctly configured before starting the service.
- For troubleshooting, check the logs using:
  ```bash
  docker logs <container-name>
  ```

## License
This project is licensed under the [MIT License](LICENSE).