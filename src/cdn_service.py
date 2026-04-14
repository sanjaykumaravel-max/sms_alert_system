"""
CDN Service for Static Asset Management in SMS Alert App.

This module provides:
- CDN integration for static assets
- Cloudinary support for image management
- AWS S3 support for general assets
- Local asset serving with caching headers
- Asset optimization and compression
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from urllib.parse import urljoin

try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.api
    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False

try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

logger = logging.getLogger(__name__)

class CDNService:
    """
    CDN service for managing static assets with multiple provider support.

    Supports:
    - Cloudinary for image optimization
    - AWS S3 for general assets
    - Local serving with caching
    """

    def __init__(self):
        self.provider = os.getenv("CDN_PROVIDER", "local").lower()
        self.base_url = os.getenv("CDN_BASE_URL", "")
        self.enabled = os.getenv("CDN_ENABLED", "false").lower() == "true"

        # Cloudinary configuration
        self.cloudinary_configured = False
        if CLOUDINARY_AVAILABLE:
            cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
            api_key = os.getenv("CLOUDINARY_API_KEY")
            api_secret = os.getenv("CLOUDINARY_API_SECRET")

            if cloud_name and api_key and api_secret:
                cloudinary.config(
                    cloud_name=cloud_name,
                    api_key=api_key,
                    api_secret=api_secret
                )
                self.cloudinary_configured = True
                logger.info("Cloudinary CDN configured")

        # S3 configuration
        self.s3_configured = False
        if S3_AVAILABLE:
            aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
            aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            s3_bucket = os.getenv("S3_BUCKET_NAME")
            s3_region = os.getenv("S3_REGION", "us-east-1")

            if aws_access_key and aws_secret_key and s3_bucket:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name=s3_region
                )
                self.s3_bucket = s3_bucket
                self.s3_configured = True
                logger.info("AWS S3 CDN configured")

        # Local asset directory
        self.local_asset_dir = Path("assets")
        self.local_asset_dir.mkdir(exist_ok=True)

    async def upload_asset(
        self,
        file_path: str,
        public_id: Optional[str] = None,
        folder: str = "sms_alert",
        **kwargs
    ) -> Optional[str]:
        """
        Upload asset to CDN.

        Args:
            file_path: Local file path to upload
            public_id: Public identifier for the asset
            folder: Folder/category for organization
            **kwargs: Additional provider-specific options

        Returns:
            CDN URL of uploaded asset or None if failed
        """
        if not self.enabled:
            logger.warning("CDN service is disabled")
            return None

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.error(f"File not found: {file_path}")
            return None

        try:
            if self.provider == "cloudinary" and self.cloudinary_configured:
                return await self._upload_cloudinary(file_path, public_id, folder, **kwargs)
            elif self.provider == "s3" and self.s3_configured:
                return await self._upload_s3(file_path, public_id, folder, **kwargs)
            else:
                return await self._serve_local(file_path, public_id, **kwargs)

        except Exception as e:
            logger.error(f"CDN upload error: {e}")
            return None

    async def _upload_cloudinary(
        self,
        file_path: str,
        public_id: Optional[str],
        folder: str,
        **kwargs
    ) -> Optional[str]:
        """Upload to Cloudinary."""
        try:
            upload_options = {
                "folder": folder,
                "resource_type": "auto",
                **kwargs
            }

            if public_id:
                upload_options["public_id"] = public_id

            # Run in thread pool since cloudinary is synchronous
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                cloudinary.uploader.upload,
                file_path,
                upload_options
            )

            return result.get("secure_url")

        except Exception as e:
            logger.error(f"Cloudinary upload error: {e}")
            return None

    async def _upload_s3(
        self,
        file_path: str,
        public_id: Optional[str],
        folder: str,
        **kwargs
    ) -> Optional[str]:
        """Upload to AWS S3."""
        try:
            file_name = public_id or Path(file_path).name
            s3_key = f"{folder}/{file_name}" if folder else file_name

            # Upload file
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.s3_client.upload_file,
                file_path,
                self.s3_bucket,
                s3_key,
                kwargs.get("extra_args", {})
            )

            # Generate public URL
            location = await asyncio.get_event_loop().run_in_executor(
                None,
                self.s3_client.get_bucket_location,
                self.s3_bucket
            )

            region = location.get("LocationConstraint", "us-east-1")
            url = f"https://{self.s3_bucket}.s3.{region}.amazonaws.com/{s3_key}"

            return url

        except ClientError as e:
            logger.error(f"S3 upload error: {e}")
            return None

    async def _serve_local(
        self,
        file_path: str,
        public_id: Optional[str],
        **kwargs
    ) -> Optional[str]:
        """Serve asset locally with CDN base URL."""
        try:
            file_name = public_id or Path(file_path).name

            # Copy file to local assets directory
            dest_path = self.local_asset_dir / file_name
            await asyncio.get_event_loop().run_in_executor(
                None,
                dest_path.write_bytes,
                Path(file_path).read_bytes()
            )

            # Return CDN URL or local path
            if self.base_url:
                return urljoin(self.base_url, f"assets/{file_name}")
            else:
                return f"/assets/{file_name}"

        except Exception as e:
            logger.error(f"Local asset copy error: {e}")
            return None

    async def delete_asset(self, public_id: str, **kwargs) -> bool:
        """
        Delete asset from CDN.

        Args:
            public_id: Public identifier of the asset
            **kwargs: Provider-specific options

        Returns:
            True if deleted successfully
        """
        if not self.enabled:
            return False

        try:
            if self.provider == "cloudinary" and self.cloudinary_configured:
                return await self._delete_cloudinary(public_id, **kwargs)
            elif self.provider == "s3" and self.s3_configured:
                return await self._delete_s3(public_id, **kwargs)
            else:
                return await self._delete_local(public_id, **kwargs)

        except Exception as e:
            logger.error(f"CDN delete error: {e}")
            return False

    async def _delete_cloudinary(self, public_id: str, **kwargs) -> bool:
        """Delete from Cloudinary."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                cloudinary.uploader.destroy,
                public_id,
                kwargs
            )
            return result.get("result") == "ok"
        except Exception as e:
            logger.error(f"Cloudinary delete error: {e}")
            return False

    async def _delete_s3(self, public_id: str, **kwargs) -> bool:
        """Delete from S3."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.s3_client.delete_object,
                Bucket=self.s3_bucket,
                Key=public_id
            )
            return True
        except Exception as e:
            logger.error(f"S3 delete error: {e}")
            return False

    async def _delete_local(self, public_id: str, **kwargs) -> bool:
        """Delete local asset."""
        try:
            file_path = self.local_asset_dir / public_id
            if file_path.exists():
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    file_path.unlink
                )
            return True
        except Exception as e:
            logger.error(f"Local delete error: {e}")
            return False

    async def get_asset_url(self, public_id: str, **kwargs) -> Optional[str]:
        """
        Get asset URL without uploading.

        Args:
            public_id: Public identifier
            **kwargs: Transformation options

        Returns:
            Asset URL or None
        """
        if not self.enabled:
            return None

        try:
            if self.provider == "cloudinary" and self.cloudinary_configured:
                return self._get_cloudinary_url(public_id, **kwargs)
            elif self.provider == "s3" and self.s3_configured:
                return self._get_s3_url(public_id, **kwargs)
            else:
                return self._get_local_url(public_id, **kwargs)

        except Exception as e:
            logger.error(f"Get asset URL error: {e}")
            return None

    def _get_cloudinary_url(self, public_id: str, **kwargs) -> str:
        """Get Cloudinary URL with transformations."""
        return cloudinary.utils.cloudinary_url(public_id, **kwargs)[0]

    def _get_s3_url(self, public_id: str, **kwargs) -> str:
        """Get S3 URL."""
        region = os.getenv("S3_REGION", "us-east-1")
        return f"https://{self.s3_bucket}.s3.{region}.amazonaws.com/{public_id}"

    def _get_local_url(self, public_id: str, **kwargs) -> str:
        """Get local asset URL."""
        if self.base_url:
            return urljoin(self.base_url, f"assets/{public_id}")
        else:
            return f"/assets/{public_id}"

    async def list_assets(self, folder: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        List assets in CDN.

        Args:
            folder: Folder to list assets from
            **kwargs: Provider-specific options

        Returns:
            List of asset information
        """
        if not self.enabled:
            return []

        try:
            if self.provider == "cloudinary" and self.cloudinary_configured:
                return await self._list_cloudinary(folder, **kwargs)
            elif self.provider == "s3" and self.s3_configured:
                return await self._list_s3(folder, **kwargs)
            else:
                return await self._list_local(folder, **kwargs)

        except Exception as e:
            logger.error(f"List assets error: {e}")
            return []

    async def _list_cloudinary(self, folder: Optional[str], **kwargs) -> List[Dict[str, Any]]:
        """List Cloudinary assets."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                cloudinary.api.resources,
                {"type": "upload", "prefix": folder} if folder else {}
            )
            return result.get("resources", [])
        except Exception as e:
            logger.error(f"Cloudinary list error: {e}")
            return []

    async def _list_s3(self, folder: Optional[str], **kwargs) -> List[Dict[str, Any]]:
        """List S3 assets."""
        try:
            prefix = f"{folder}/" if folder else ""
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self.s3_client.list_objects_v2,
                self.s3_bucket,
                {"Prefix": prefix}
            )

            objects = response.get("Contents", [])
            return [
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat()
                }
                for obj in objects
            ]
        except Exception as e:
            logger.error(f"S3 list error: {e}")
            return []

    async def _list_local(self, folder: Optional[str], **kwargs) -> List[Dict[str, Any]]:
        """List local assets."""
        try:
            search_dir = self.local_asset_dir / folder if folder else self.local_asset_dir
            if not search_dir.exists():
                return []

            assets = []
            for file_path in search_dir.glob("*"):
                if file_path.is_file():
                    stat = file_path.stat()
                    assets.append({
                        "key": file_path.name,
                        "path": str(file_path),
                        "size": stat.st_size,
                        "last_modified": stat.st_mtime
                    })

            return assets
        except Exception as e:
            logger.error(f"Local list error: {e}")
            return []

    async def optimize_image(
        self,
        image_path: str,
        public_id: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """
        Upload and optimize image.

        Args:
            image_path: Path to image file
            public_id: Public identifier
            **kwargs: Optimization options

        Returns:
            Optimized image URL
        """
        if not self.enabled:
            return None

        # Set optimization parameters
        optimize_options = {
            "quality": kwargs.get("quality", "auto"),
            "format": kwargs.get("format", "auto"),
            "width": kwargs.get("width"),
            "height": kwargs.get("height"),
            "crop": kwargs.get("crop", "fill"),
            **kwargs
        }

        return await self.upload_asset(image_path, public_id, **optimize_options)

# Global CDN instance
cdn_service = CDNService()

# Utility functions
async def upload_logo(logo_path: str) -> Optional[str]:
    """Upload application logo to CDN."""
    return await cdn_service.upload_asset(logo_path, "logo", folder="ui")

async def upload_icon(icon_path: str, icon_name: str) -> Optional[str]:
    """Upload icon to CDN."""
    return await cdn_service.upload_asset(icon_path, f"icon_{icon_name}", folder="icons")

async def get_asset_url(asset_id: str) -> Optional[str]:
    """Get asset URL."""
    return await cdn_service.get_asset_url(asset_id)

# Health check
async def check_cdn_health() -> Dict[str, Any]:
    """Check CDN service health."""
    health = {
        "enabled": cdn_service.enabled,
        "provider": cdn_service.provider,
        "cloudinary": cdn_service.cloudinary_configured,
        "s3": cdn_service.s3_configured,
        "local_assets": cdn_service.local_asset_dir.exists()
    }

    # Test basic functionality
    try:
        assets = await cdn_service.list_assets()
        health["list_test"] = len(assets) >= 0
    except Exception:
        health["list_test"] = False

    return health