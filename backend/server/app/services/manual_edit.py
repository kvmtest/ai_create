"""
Manual edit service for applying edits to generated assets
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from PIL import Image, ImageEnhance, ImageDraw, ImageFont
import os
import json
import logging
import shutil
from pathlib import Path

from app.models.asset import GeneratedAsset, Asset
from app.models.admin import AppSetting, TextStyleSet
from app.models.project import Project
from app.schemas.asset import ManualEdit
from app.services.config_manager import ConfigManager
from app.core.exceptions import ValidationError, NotFoundError, ForbiddenError

logger = logging.getLogger(__name__)


class ManualEditService:
    def __init__(self, db: Session):
        self.db = db
        self.config_manager = ConfigManager(db)

    def apply_manual_edits(
        self, 
        generated_asset_id: UUID, 
        edits: ManualEdit, 
        user_id: UUID
    ) -> GeneratedAsset:
        """Apply manual edits to a generated asset."""
        logger.info(f"Applying manual edits to asset {generated_asset_id} for user {user_id}")
        
        try:
            # Get the generated asset
            generated_asset = self._get_generated_asset(generated_asset_id, user_id)
            
            # Validate edits against admin rules
            self._validate_edits(edits)
            
            # Validate edit parameters
            self._validate_edit_parameters(edits)
            
            # Load the current image
            image_path = generated_asset.storage_path
            if not os.path.exists(image_path):
                raise NotFoundError(f"Asset file not found at path: {image_path}")
            
            # Backup current version before editing
            backup_path = self._backup_current_version(image_path)
            
            try:
                # Apply edits to the image
                edited_image_path = self._process_image_edits(image_path, edits, generated_asset)
                
                # Create edit history entry
                edit_history = self._create_edit_history_entry(edits, generated_asset.manual_edits)
                
                # Update the generated asset
                old_path = generated_asset.storage_path
                generated_asset.storage_path = edited_image_path
                generated_asset.manual_edits = edit_history
                
                self.db.commit()
                self.db.refresh(generated_asset)
                
                # Clean up old file if different from new one
                if old_path != edited_image_path and os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except OSError as e:
                        logger.warning(f"Failed to remove old file {old_path}: {e}")
                
                logger.info(f"Successfully applied manual edits to asset {generated_asset_id}")
                return generated_asset
                
            except Exception as e:
                # Restore backup if edit processing failed
                if backup_path and os.path.exists(backup_path):
                    shutil.move(backup_path, image_path)
                raise
                
        except Exception as e:
            logger.error(f"Failed to apply manual edits to asset {generated_asset_id}: {e}")
            self.db.rollback()
            raise

    def _get_generated_asset(self, generated_asset_id: UUID, user_id: UUID) -> GeneratedAsset:
        """Get generated asset ensuring user has access."""
        generated_asset = self.db.query(GeneratedAsset).join(
            Asset, GeneratedAsset.original_asset_id == Asset.id
        ).join(
            Project, Asset.project_id == Project.id
        ).filter(
            and_(
                GeneratedAsset.id == generated_asset_id,
                Project.user_id == user_id
            )
        ).first()
        
        if not generated_asset:
            raise NotFoundError("Generated asset not found or access denied")
        
        return generated_asset

    def _validate_edits(self, edits: ManualEdit) -> None:
        """Validate edits against admin rules."""
        # Use config manager for admin rules
        if not self.config_manager.is_manual_editing_enabled():
            raise ForbiddenError("Manual editing is disabled by administrator")
        
        # Validate crop settings
        if edits.crop and not self.config_manager.is_cropping_enabled():
            raise ForbiddenError("Cropping is disabled by administrator")
        
        # Validate saturation settings
        if edits.saturation is not None and not self.config_manager.is_saturation_enabled():
            raise ForbiddenError("Saturation adjustment is disabled by administrator")
        
        # Validate text/logo overlays
        if (edits.text_overlays or edits.logo_overlays) and not self.config_manager.is_text_logo_enabled():
            raise ForbiddenError("Text and logo overlays are disabled by administrator")
        
        # Validate overlay limits with sensible defaults
        if edits.text_overlays:
            max_text_overlays = 10  # Default limit
            if len(edits.text_overlays) > max_text_overlays:
                raise ValidationError(f"Maximum {max_text_overlays} text overlays allowed")
        
        if edits.logo_overlays:
            max_logo_overlays = 5  # Default limit
            if len(edits.logo_overlays) > max_logo_overlays:
                raise ValidationError(f"Maximum {max_logo_overlays} logo overlays allowed")

    def _validate_edit_parameters(self, edits: ManualEdit) -> None:
        """Validate edit parameters for correctness."""
        # Validate crop parameters
        if edits.crop:
            crop = edits.crop
            if not (0 <= crop.x <= 1 and 0 <= crop.y <= 1):
                raise ValidationError("Crop x and y coordinates must be between 0 and 1")
            if not (0 < crop.width <= 1 and 0 < crop.height <= 1):
                raise ValidationError("Crop width and height must be between 0 and 1")
            if crop.x + crop.width > 1 or crop.y + crop.height > 1:
                raise ValidationError("Crop area extends beyond image boundaries")
        
        # Validate saturation range
        if edits.saturation is not None:
            if not (-1.0 <= edits.saturation <= 1.0):
                raise ValidationError("Saturation value must be between -1.0 and 1.0")
        
        # Validate text overlays
        if edits.text_overlays:
            for i, overlay in enumerate(edits.text_overlays):
                if not overlay.text or not overlay.text.strip():
                    raise ValidationError(f"Text overlay {i+1} cannot be empty")
                if not (0 <= overlay.x <= 1 and 0 <= overlay.y <= 1):
                    raise ValidationError(f"Text overlay {i+1} position must be between 0 and 1")
        
        # Validate logo overlays
        if edits.logo_overlays:
            for i, overlay in enumerate(edits.logo_overlays):
                if not overlay.logo_path:
                    raise ValidationError(f"Logo overlay {i+1} must have a logo path")
                if not (0 <= overlay.x <= 1 and 0 <= overlay.y <= 1):
                    raise ValidationError(f"Logo overlay {i+1} position must be between 0 and 1")
                if overlay.width is not None and overlay.width <= 0:
                    raise ValidationError(f"Logo overlay {i+1} width must be positive")
                if overlay.height is not None and overlay.height <= 0:
                    raise ValidationError(f"Logo overlay {i+1} height must be positive")

    def _backup_current_version(self, image_path: str) -> Optional[str]:
        """Create a backup of the current version before editing."""
        try:
            backup_path = f"{image_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(image_path, backup_path)
            return backup_path
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
            return None

    def _process_image_edits(
        self, 
        image_path: str, 
        edits: ManualEdit, 
        generated_asset: GeneratedAsset
    ) -> str:
        """Process and apply image edits."""
        try:
            # Load the image
            with Image.open(image_path) as img:
                logger.debug(f"Processing image {image_path} with mode {img.mode}, size {img.size}")
                
                # Convert to RGB if necessary
                if img.mode not in ('RGB', 'RGBA'):
                    logger.debug(f"Converting image from {img.mode} to RGB")
                    img = img.convert('RGB')
                
                # Apply edits in order: crop -> saturation -> overlays
                # This order ensures overlays are applied to the final cropped/adjusted image
                
                # Apply crop if specified
                if edits.crop:
                    logger.debug(f"Applying crop: {edits.crop}")
                    img = self._apply_crop(img, edits.crop)
                
                # Apply saturation if specified
                if edits.saturation is not None:
                    logger.debug(f"Applying saturation: {edits.saturation}")
                    img = self._apply_saturation(img, edits.saturation)
                
                # Apply text overlays if specified
                if edits.text_overlays:
                    logger.debug(f"Applying {len(edits.text_overlays)} text overlays")
                    img = self._apply_text_overlays(img, edits.text_overlays)
                
                # Apply logo overlays if specified
                if edits.logo_overlays:
                    logger.debug(f"Applying {len(edits.logo_overlays)} logo overlays")
                    img = self._apply_logo_overlays(img, edits.logo_overlays)
                
                # Generate new filename with timestamp
                original_path = Path(image_path)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_filename = f"{original_path.stem}_edited_{timestamp}{original_path.suffix}"
                new_path = original_path.parent / new_filename
                
                # Ensure directory exists
                new_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Save the edited image with appropriate format
                save_kwargs = {"quality": 95, "optimize": True}
                if original_path.suffix.lower() == '.png':
                    save_kwargs = {"optimize": True}
                
                img.save(new_path, **save_kwargs)
                logger.debug(f"Saved edited image to {new_path}")
                
                return str(new_path)
                
        except Exception as e:
            logger.error(f"Failed to process image edits for {image_path}: {e}")
            raise ValidationError(f"Failed to process image edits: {str(e)}")

    def _apply_crop(self, img: Image.Image, crop_params) -> Image.Image:
        """Apply crop transformation to image."""
        width, height = img.size
        
        # Convert relative coordinates to absolute
        left = int(crop_params.x * width)
        top = int(crop_params.y * height)
        crop_width = int(crop_params.width * width)
        crop_height = int(crop_params.height * height)
        
        right = left + crop_width
        bottom = top + crop_height
        
        # Ensure coordinates are within image bounds
        left = max(0, min(left, width - 1))
        top = max(0, min(top, height - 1))
        right = max(left + 1, min(right, width))
        bottom = max(top + 1, min(bottom, height))
        
        # Validate that we have a valid crop area
        if right <= left or bottom <= top:
            raise ValidationError("Invalid crop area: resulting crop would be empty")
        
        logger.debug(f"Cropping image from {width}x{height} to {right-left}x{bottom-top} at ({left},{top})")
        return img.crop((left, top, right, bottom))

    def _apply_saturation(self, img: Image.Image, saturation_value: float) -> Image.Image:
        """Apply saturation adjustment to image."""
        # Clamp saturation value between -1 and 1
        saturation_value = max(-1.0, min(1.0, saturation_value))
        
        # Convert to enhancement factor (0.0 = grayscale, 1.0 = original, 2.0 = double saturation)
        enhancement_factor = 1.0 + saturation_value
        enhancement_factor = max(0.0, enhancement_factor)
        
        enhancer = ImageEnhance.Color(img)
        return enhancer.enhance(enhancement_factor)

    def _apply_text_overlays(self, img: Image.Image, text_overlays: List) -> Image.Image:
        """Apply text overlays to image."""
        draw = ImageDraw.Draw(img)
        
        for i, overlay in enumerate(text_overlays):
            try:
                text = overlay.text.strip()
                if not text:
                    logger.warning(f"Skipping empty text overlay {i+1}")
                    continue
                
                # Get text style
                font_config = self._get_text_style(overlay.style_set_id, overlay.style_type)
                
                # Position (relative coordinates)
                x = overlay.x * img.width
                y = overlay.y * img.height
                
                # Load font
                font = self._load_font(font_config["font_family"], font_config["font_size"])
                fill_color = font_config.get("color", "#FFFFFF")
                
                # Add text stroke for better visibility
                stroke_width = font_config.get("stroke_width", 0)
                stroke_fill = font_config.get("stroke_color", "#000000")
                
                # Draw text with optional stroke
                draw.text(
                    (x, y), 
                    text, 
                    font=font, 
                    fill=fill_color, 
                    anchor="mm",
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill if stroke_width > 0 else None
                )
                
                logger.debug(f"Applied text overlay {i+1}: '{text}' at ({x:.1f}, {y:.1f})")
                
            except Exception as e:
                logger.error(f"Failed to apply text overlay {i+1}: {e}")
                # Continue with other overlays
                continue
        
        return img

    def _load_font(self, font_family: str, font_size: int) -> ImageFont.ImageFont:
        """Load font with fallback to default."""
        try:
            # Try to load the specified font
            return ImageFont.truetype(font_family, font_size)
        except (OSError, IOError):
            try:
                # Try common font paths
                common_fonts = [
                    f"/usr/share/fonts/truetype/dejavu/{font_family}",
                    f"/System/Library/Fonts/{font_family}",
                    f"C:\\Windows\\Fonts\\{font_family}",
                ]
                for font_path in common_fonts:
                    if os.path.exists(font_path):
                        return ImageFont.truetype(font_path, font_size)
            except (OSError, IOError):
                pass
            
            # Fallback to default font
            logger.warning(f"Could not load font {font_family}, using default")
            return ImageFont.load_default()

    def _apply_logo_overlays(self, img: Image.Image, logo_overlays: List) -> Image.Image:
        """Apply logo overlays to image."""
        for i, overlay in enumerate(logo_overlays):
            try:
                logo_path = overlay.logo_path
                if not logo_path or not os.path.exists(logo_path):
                    logger.warning(f"Logo overlay {i+1}: file not found at {logo_path}")
                    continue
                
                with Image.open(logo_path) as logo:
                    # Convert logo to RGBA for consistent handling
                    if logo.mode != 'RGBA':
                        logo = logo.convert('RGBA')
                    
                    # Resize logo if specified
                    original_size = logo.size
                    if overlay.width is not None or overlay.height is not None:
                        new_width = overlay.width or int(original_size[0] * (overlay.height / original_size[1]))
                        new_height = overlay.height or int(original_size[1] * (overlay.width / original_size[0]))
                        
                        # Ensure minimum size
                        new_width = max(1, new_width)
                        new_height = max(1, new_height)
                        
                        logo = logo.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        logger.debug(f"Resized logo {i+1} from {original_size} to {logo.size}")
                    
                    # Position (relative coordinates, centered on the point)
                    x = int(overlay.x * img.width - logo.width / 2)
                    y = int(overlay.y * img.height - logo.height / 2)
                    
                    # Ensure logo stays within image bounds
                    x = max(0, min(x, img.width - logo.width))
                    y = max(0, min(y, img.height - logo.height))
                    
                    # Apply logo with transparency
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    
                    # Create a new image for compositing
                    overlay_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
                    overlay_img.paste(logo, (x, y))
                    
                    # Composite the overlay onto the main image
                    img = Image.alpha_composite(img, overlay_img)
                    
                    logger.debug(f"Applied logo overlay {i+1} at ({x}, {y})")
            
            except Exception as e:
                logger.error(f"Failed to apply logo overlay {i+1}: {e}")
                continue
        
        # Convert back to RGB if no transparency is needed
        if img.mode == 'RGBA':
            # Create a white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
            img = background
        
        return img

    def _get_text_style(self, style_set_id: UUID, style_type: str) -> Dict[str, Any]:
        """Get text style configuration from style set."""
        try:
            # Get text style set
            style_set = self.db.query(TextStyleSet).filter(
                TextStyleSet.id == style_set_id
            ).first()
            
            if not style_set:
                logger.warning(f"Text style set {style_set_id} not found")
                return {
                    "font_family": "arial.ttf",
                    "font_size": 24,
                    "color": "#FFFFFF",
                    "alignment": "center"
                }
            
            # Get style configuration
            styles = style_set.styles
            style_config = styles.get(style_type, {})
            
            # Merge with defaults
            return {
                "font_family": style_config.get("font_family", "arial.ttf"),
                "font_size": style_config.get("font_size", 24),
                "color": style_config.get("color", "#FFFFFF"),
                "alignment": style_config.get("alignment", "center")
            }
            
        except Exception as e:
            logger.error(f"Error getting text style: {e}")
            return {
                "font_family": "arial.ttf",
                "font_size": 24,
                "color": "#FFFFFF",
                "alignment": "center"
            }

    def _create_edit_history_entry(
        self, 
        edits: ManualEdit, 
        current_history: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new edit history entry."""
        if not current_history:
            current_history = {"history": [], "current_version": -1}
        
        # Create edit summary for better tracking
        edit_summary = []
        if edits.crop:
            edit_summary.append(f"crop({edits.crop.x:.2f},{edits.crop.y:.2f},{edits.crop.width:.2f},{edits.crop.height:.2f})")
        if edits.saturation is not None:
            edit_summary.append(f"saturation({edits.saturation:.2f})")
        if edits.text_overlays:
            edit_summary.append(f"text_overlays({len(edits.text_overlays)})")
        if edits.logo_overlays:
            edit_summary.append(f"logo_overlays({len(edits.logo_overlays)})")
        
        # Create new history entry
        new_entry = {
            "version": len(current_history.get("history", [])),
            "timestamp": datetime.utcnow().isoformat(),
            "edits": edits.dict(exclude_unset=True),
            "summary": ", ".join(edit_summary) if edit_summary else "no_changes",
            "edit_count": len(edit_summary)
        }
        
        # Add to history
        history = current_history.get("history", [])
        history.append(new_entry)
        
        # Limit history size to prevent excessive storage
        max_history_size = 50
        if len(history) > max_history_size:
            history = history[-max_history_size:]
            # Update version numbers
            for i, entry in enumerate(history):
                entry["version"] = i
        
        return {
            "history": history,
            "current_version": new_entry["version"],
            "total_edits": len(history),
            "last_modified": datetime.utcnow().isoformat()
        }

    # def _get_original_asset_path(self, generated_asset: GeneratedAsset) -> str:
    #     """Get the path to the original (unedited) version of the asset."""
    #     # The original asset is the source asset that was used to generate this asset
    #     return generated_asset.original_asset.storage_path

    # def get_edit_statistics(self, generated_asset_id: UUID, user_id: UUID) -> Dict[str, Any]:
    #     """Get statistics about edits applied to an asset."""
    #     generated_asset = self._get_generated_asset(generated_asset_id, user_id)
    #
    #     edit_history = generated_asset.manual_edits.get("history", [])
    #     if not edit_history:
    #         return {
    #             "total_versions": 0,
    #             "current_version": -1,
    #             "edit_types_used": [],
    #             "total_edits": 0
    #         }
    #
    #     # Analyze edit types used
    #     edit_types = set()
    #     total_text_overlays = 0
    #     total_logo_overlays = 0
    #
    #     for entry in edit_history:
    #         edits = entry.get("edits", {})
    #         if edits.get("crop"):
    #             edit_types.add("crop")
    #         if edits.get("saturation") is not None:
    #             edit_types.add("saturation")
    #         if edits.get("text_overlays"):
    #             edit_types.add("text_overlays")
    #             total_text_overlays += len(edits["text_overlays"])
    #         if edits.get("logo_overlays"):
    #             edit_types.add("logo_overlays")
    #             total_logo_overlays += len(edits["logo_overlays"])
    #
    #     return {
    #         "total_versions": len(edit_history),
    #         "current_version": generated_asset.manual_edits.get("current_version", len(edit_history) - 1),
    #         "edit_types_used": list(edit_types),
    #         "total_edits": len(edit_history),
    #         "total_text_overlays": total_text_overlays,
    #         "total_logo_overlays": total_logo_overlays,
    #         "last_modified": generated_asset.manual_edits.get("last_modified"),
    #         "has_reverts": "last_revert" in generated_asset.manual_edits
    #     }