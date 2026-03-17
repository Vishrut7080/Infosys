FROM python:3.12-slim

WORKDIR /app

# Install OS dependencies required by some python packages (like building wheels, sqlite, networking tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv/pip to manage dependencies
RUN pip install --upgrade pip

# Copy the pyproject.toml
COPY pyproject.toml ./

# Install project dependencies directly via pip since it's a simple setup
RUN pip install .

# Copy the rest of the application
COPY . .

# Expose Flask default port
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=Mail.web_login
ENV FLASK_ENV=production

# The default command to run the application (assuming we run main.py which starts Flask)
# Or we can just start flask directly, but wait - the orchestrator logic needs to run. 
CMD ["python", "main.py"]