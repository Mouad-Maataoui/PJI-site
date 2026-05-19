import boto3
import logging
from botocore.config import Config
from app.core.config import settings
import os
from PIL import Image
import io
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

#
# account_id = "75e63ae589c6226bc84f2ca32eb40a7f"
# access_key_id = "534361d9d943f59c5d896bf97fd09340"
# secret_access_key = "fed6109f249a4a0b217e9c24fb6d1563d7208bd7f3c3bc998fe9f1469db659cc"
# bucket_name = "pji-2025-backend-remove"
# account_id = settings.R2_ACCOUNT_ID
# access_key_id = settings.R2_ACCESS_KEY_ID
# secret_access_key = settings.R2_SECRET_ACCESS_KEY
# bucket_name = settings.R2_BUCKET_NAME
# print(account_id)

class S3Manager():
    def __init__(self, account_id, access_key_id, secret_access_key, bucket_name, cloud_endpoint):
        self.account_id = account_id
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.bucket_name = bucket_name
        self.cloud_endpoint = cloud_endpoint

    def get_r2_client(self):
        return boto3.client(
            's3',
            endpoint_url=f'http://{self.cloud_endpoint}',
            aws_access_key_id=settings.CLOUD_ACCESS_KEY_ID,
            aws_secret_access_key=settings.CLOUD_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4'),
            region_name='auto'  # Required but ignored by R2
        )

    def upload_file(self,file_path, object_name=None):
        """Upload a file to an R2 bucket

        :param file_path: File to upload
        :param object_name: S3 object name. If not specified, file_name is used
        :return: True if file was uploaded, else False
        """
        # If S3 object_name was not specified, use file_name
        s3 = self.get_r2_client()
        if object_name is None:
            object_name = file_path

        try:
            s3.upload_file(file_path, self.bucket_name, object_name)
            logger.info(f"File {file_path} uploaded to {object_name}")
            return True
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
        logger.warning("Not uploaded")
        return False
    
    def upload_from_memory(self, file_data, object_name):
        """Upload data directly from memory

        :param file_data: Binary data to upload
        :param object_name: S3 object name
        """
        s3 = self.get_r2_client()
        try:
            s3.put_object(Bucket=self.bucket_name, Key=object_name, Body=file_data)
            logger.info(f"Data uploaded to {object_name}")
            return True
        except Exception as e:
            logger.error(f"Error uploading data: {e}")
        return False
    
    def download_file(self, object_name, file_path=None):
        """Download a file from an R2 bucket

        :param object_name: S3 object name
        :param file_path: Local path to save to. If not specified, object_name is used
        :return: True if file was downloaded, else False
        """
        s3 = self.get_r2_client()
        # If file_path was not specified, use object_name
        if file_path is None:
            file_path = object_name
        try:
            s3.download_file(self.bucket_name, object_name, file_path)
            logger.info(f"File {object_name} downloaded to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
        return False

    def download_to_memory(self, object_name, output_path):
        """Download data directly to memory

        :param object_name: S3 object name
        :return: File data as bytes or None if error
        """
        s3 = self.get_r2_client()
        try:
            response = s3.get_object(Bucket=self.bucket_name, Key=object_name)
            metadata = response["Metadata"]
            data = response['Body'].read()

            # Load image
            img = Image.open(io.BytesIO(data))
            orig_size = (
                int(metadata["orig-width"]),
                int(metadata["orig-height"])
            )
            img = img.resize(orig_size, Image.Resampling.LANCZOS)

            # Save as WebP or convert to another format
            img.save(output_path, format="WEBP")
            logger.info(f"Data downloaded from {object_name}")
            
        except Exception as e:
            logger.error(f"Error downloading data: {e}")
            return None


    def list_objects(self, prefix=''):
        """List objects in the bucket

        :param prefix: Only list objects with this prefix
        """
        s3 = self.get_r2_client()
        try:
            response = s3.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            if 'Contents' in response:
                for obj in response['Contents']:
                    logger.info(obj['Key'])
            return response.get('Contents', [])
        except Exception as e:
            logger.erro(f"Error listing objects: {e}")
            return []

    def generate_presigned_url(self, object_name, expiration=3600):
        """Generate a pre-signed URL to share an S3 object

        :param object_name: S3 object name
        :param expiration: Time in seconds for the pre-signed URL to remain valid
        :return: Pre-signed URL as string. If error, returns None.
        """
        s3 = self.get_r2_client()
        try:
            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_name},
                ExpiresIn=expiration
            )
            logger.info(f"Generated pre-signed URL for {object_name}")
            return url
        except Exception as e:
            logger.errory(f"Error generating pre-signed URL: {e}")
            return None

# s3manager = S3Manager(account_id, access_key_id, secret_access_key, bucket_name)
# if __name__ == '__main__':
#     # s3manager.upload_file('culture.jpg', 'remote_culture.jpg')
#     # s3manager.download_file('remote_culture.jpg')
#     print(s3manager.generate_presigned_url('remote.txt'))
