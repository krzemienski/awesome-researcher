FROM python:3.12-slim

# Install Node.js for awesome-lint
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    ca-certificates \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install awesome-lint
RUN npm install -g awesome-lint

# Install Poetry
RUN pip install poetry

# Set up working directory
WORKDIR /app

# Copy .env file if it exists
COPY [".env", ".env"]

# Copy source code
COPY . .

# Configure poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi

# Entrypoint
ENTRYPOINT ["./build-and-run.sh"]
