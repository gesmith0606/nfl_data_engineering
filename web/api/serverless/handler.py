"""
AWS Lambda handler wrapping the FastAPI application via Mangum.

Deploy this as the Lambda function handler: ``handler.handler``.
"""

from mangum import Mangum

from web.api.main import app

handler = Mangum(app, lifespan="off")
