FROM tiangolo/uwsgi-nginx-flask:python3.10

# Copy requirements
COPY requirements.txt /tmp/

# Install dependencies
RUN pip install -r /tmp/requirements.txt
RUN pip install flask_sqlalchemy cryptography

# Copy app code
COPY . .

# Optional: Add non-root user (but don't switch to it)
RUN adduser --disabled-password --gecos '' appuser

# Drop privileges for uWSGI only (safe)
ENV UWSGI_UID=appuser
ENV UWSGI_GID=appuser
