#E:\Freshify\FreshiFy_Mobile_App_Backend\Dockerfile
# Use official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app files into the container
COPY . .

# Expose port 5000 for Flask
EXPOSE 5000

# Command to run the Flask app
CMD ["python", "main.py"]
