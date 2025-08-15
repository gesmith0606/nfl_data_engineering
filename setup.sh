#!/bin/bash

# Setup script for NFL Data Engineering Pipeline
echo "🏈 Setting up NFL Data Engineering Pipeline..."

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install requirements
echo "📥 Installing Python dependencies..."
pip install --upgrade pip
pip install -r nfl_data_engineering/requirements.txt

# Copy environment file
echo "⚙️ Setting up environment variables..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✏️ Please edit .env file with your actual AWS and Databricks credentials"
fi

# Create local data directory
echo "📁 Creating local data directory..."
mkdir -p data/{bronze,silver,gold}

echo "✅ Setup complete!"
echo "📝 Next steps:"
echo "   1. Edit .env file with your AWS S3 bucket and Databricks details"
echo "   2. Configure your AWS credentials (aws configure)"
echo "   3. Test the pipeline with: python -m pytest tests/"
echo "   4. Run notebooks in Databricks or use Databricks Connect"
