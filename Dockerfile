FROM python:3.12-slim
WORKDIR /app
COPY tracker.py .
# Le fournisseur (Render, Fly.io...) injecte PORT automatiquement.
EXPOSE 8000
CMD ["python", "tracker.py"]
