FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install Node.js for awesome-lint
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install awesome-lint globally
RUN npm install -g awesome-lint

# Install Poetry
RUN pip install poetry==1.7.1

# Copy poetry configuration files
COPY pyproject.toml ./

# Configure poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi --no-dev

# Copy the rest of the application
COPY . .

# Create directory for output
RUN mkdir -p runs

ENTRYPOINT ["./build-and-run.sh"]
