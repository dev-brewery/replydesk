# replydesk API bridge. python:3.12-slim is multi-arch (arm64 builds natively
# on the Oracle A1 host). Stdlib only — no pip install step.
#
# The deploy directory is self-contained by contract (app code is not in it),
# so the image fetches the public repo tarball at build time. Tarball route
# avoids installing git.
ARG REPO=https://github.com/dev-brewery/replydesk
ARG REF=main

FROM python:3.12-slim
ARG REPO
ARG REF

ADD ${REPO}/archive/${REF}.tar.gz /tmp

WORKDIR /app
RUN cp -r /tmp/replydesk-${REF}/replydesk /tmp/replydesk-${REF}/app.py ./ \
    && rm -rf /tmp/replydesk-${REF}

# No .env is copied into the image; compose's env_file injects it at runtime.
EXPOSE 8010
CMD ["python", "app.py", "--serve-api", "--host", "0.0.0.0", "--port", "8010", "--env", ".env"]
