FROM docker.io/cloudflare/sandbox:0.7.0

# Python packages JAI skills routinely need
RUN pip install --no-cache-dir \
    httpx \
    pydantic \
    google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 \
    notion-client \
    slack-sdk \
    supabase \
    beautifulsoup4 \
    python-dateutil

# Node packages (TS skills)
RUN npm install -g typescript tsx

EXPOSE 8080
