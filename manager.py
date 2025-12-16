"""
Olympics Countdown Plugin for LEDMatrix

Displays a countdown to the next Olympics (summer or winter) with an Olympics logo.
Once the Olympics starts, displays a countdown to the closing ceremony.

Features:
- Automatically determines next Olympics (summer or winter)
- Countdown to opening ceremony
- Countdown to closing ceremony once Olympics starts
- Olympics logo display (image or programmatic fallback)
- Adaptive text display for different screen sizes

API Version: 1.0.0
"""

import logging
from datetime import date, datetime
from typing import Dict, Any, Tuple, Optional
from pathlib import Path
from PIL import Image, ImageDraw

from src.plugin_system.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


# Olympics dates - opening and closing ceremonies
# Format: (year, month, day, type, location)
OLYMPICS_DATES = [
    # Winter Olympics 2026 - Milan-Cortina
    (2026, 2, 6, "winter", "Milan-Cortina"),
    (2026, 2, 22, "winter", "Milan-Cortina"),
    # Summer Olympics 2028 - Los Angeles
    (2028, 7, 14, "summer", "Los Angeles"),
    (2028, 7, 30, "summer", "Los Angeles"),
    # Winter Olympics 2030 - TBD (placeholder dates)
    (2030, 2, 8, "winter", "TBD"),
    (2030, 2, 24, "winter", "TBD"),
    # Summer Olympics 2032 - Brisbane
    (2032, 7, 23, "summer", "Brisbane"),
    (2032, 8, 8, "summer", "Brisbane"),
]


class OlympicsCountdownPlugin(BasePlugin):
    """
    Olympics countdown plugin that displays days until the next Olympics.
    
    Configuration options:
        enabled (bool): Enable/disable plugin
        display_duration (number): Seconds to display (default: 15)
        logo_size (number, optional): Logo size in pixels (auto-calculated)
        text_color (array): RGB text color [R, G, B] (default: [255, 255, 255])
    """
    
    def __init__(self, plugin_id: str, config: Dict[str, Any],
                 display_manager, cache_manager, plugin_manager):
        """Initialize the Olympics countdown plugin."""
        super().__init__(plugin_id, config, display_manager, cache_manager, plugin_manager)
        
        # Parse colors - convert to integers in case they come from JSON as strings
        def _parse_color(name, default):
            raw = config.get(name, default)
            try:
                return tuple(int(c) for c in raw)
            except (ValueError, TypeError):
                try:
                    return tuple(raw)
                except TypeError:
                    return raw
        
        self.text_color = _parse_color('text_color', [255, 255, 255])  # White
        self.logo_size = config.get('logo_size')  # None = auto-calculate
        
        # State
        self.days_until = 0
        self.is_olympics_active = False
        self.current_olympics = None
        self.countdown_type = "opening"  # "opening" or "closing"
        self.logo_image = None
        self.last_calculated_date = None
        self.last_displayed_message = None  # Track last displayed to prevent unnecessary redraws
        
        # Load logo image if available
        self._load_logo_image()
        
        self.logger.info("Olympics countdown plugin initialized")
    
    def _load_logo_image(self) -> None:
        """Load Olympics logo image from plugin directory."""
        try:
            plugin_dir = Path(__file__).parent
            
            # Try common image filenames
            possible_names = [
                "olympics-logo.png",
                "olympics logo.png",
                "olympics-icon.png",
                "logo.png",
                "assets/olympics-logo.png",
                "assets/logo.png"
            ]
            
            for name in possible_names:
                logo_path = plugin_dir / name
                if logo_path.exists():
                    self.logo_image = Image.open(logo_path)
                    self.logger.info(f"Loaded Olympics logo image from {logo_path}")
                    return
            
            self.logger.debug("Olympics logo image not found, will use programmatic drawing")
            self.logo_image = None
        except Exception as e:
            self.logger.warning(f"Error loading logo image: {e}, will use programmatic drawing")
            self.logo_image = None
    
    def _get_next_olympics(self) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Determine the next Olympics and whether we're counting down to opening or closing.
        
        Returns:
            Tuple of (olympics_info, is_active)
            - olympics_info: Dict with 'opening', 'closing', 'type', 'location', or None
            - is_active: True if Olympics is currently happening, False if counting down
        """
        today = date.today()
        
        # Find the next Olympics
        # Group by Olympics (opening/closing pairs)
        olympics_events = []
        for i in range(0, len(OLYMPICS_DATES), 2):
            if i + 1 < len(OLYMPICS_DATES):
                opening = OLYMPICS_DATES[i]
                closing = OLYMPICS_DATES[i + 1]
                olympics_events.append({
                    'opening': date(opening[0], opening[1], opening[2]),
                    'closing': date(closing[0], closing[1], closing[2]),
                    'type': opening[3],
                    'location': opening[4]
                })
        
        # Find the next relevant Olympics
        for event in olympics_events:
            # If we're before the opening, countdown to opening
            if today < event['opening']:
                return event, False
            # If we're between opening and closing, countdown to closing
            elif event['opening'] <= today <= event['closing']:
                return event, True
        
        # If we've passed all known Olympics, return the last one (shouldn't happen often)
        if olympics_events:
            return olympics_events[-1], False
        
        return None, False
    
    def _calculate_days_until(self) -> Tuple[int, bool, Optional[Dict[str, Any]], str]:
        """
        Calculate days until next Olympics event.

        Returns:
            Tuple of (days_until, is_active, olympics_info, countdown_type)
            - days_until: Days until target event (positive = future, 0 = today, negative = past)
            - is_active: True if Olympics is currently happening
            - olympics_info: Dict with Olympics details or None
            - countdown_type: "opening" or "closing"
        """
        olympics_info, is_active = self._get_next_olympics()
        
        if not olympics_info:
            return 0, False, None, "opening"
        
        today = date.today()
        
        if is_active:
            # Countdown to closing ceremony
            days_diff = (olympics_info['closing'] - today).days
            return days_diff, True, olympics_info, "closing"
        else:
            # Countdown to opening ceremony
            days_diff = (olympics_info['opening'] - today).days
            return days_diff, False, olympics_info, "opening"
    
    def _calculate_text_layout(self, width: int, height: int, lines: list) -> Dict[str, Any]:
        """
        Calculate optimal text layout parameters based on display dimensions.

        Args:
            width: Display width in pixels
            height: Display height in pixels
            lines: List of text lines to display

        Returns:
            Dict with layout parameters:
            - font: Font to use
            - line_height: Height per line in pixels
            - total_text_height: Total height needed for all lines
            - start_y: Starting Y position for first line
            - use_small_font: Boolean indicating if small font should be used
        """
        # Calculate available space for text (right half of display)
        left_half_width = width // 2
        right_half_width = width - left_half_width
        available_text_width = right_half_width - 4  # Small margin

        # Calculate available height
        available_text_height = height - 4  # Small margins top/bottom

        # Determine font to use based on available space and number of lines
        num_lines = len(lines)

        # Calculate text dimensions for different font options
        font_options = [
            ('regular', self.display_manager.regular_font, False),
            ('small', self.display_manager.small_font, True),
            ('extra_small', self.display_manager.extra_small_font, True)
        ]

        best_font = None
        best_line_height = 8
        best_total_height = 0
        best_use_small = False

        # Find the best font that fits all lines within available space
        for font_name, font, use_small in font_options:
            # Get average character width for this font
            test_text = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            try:
                avg_char_width = self.display_manager.get_text_width(test_text, font) / len(test_text)
            except:
                avg_char_width = 6 if use_small else 8  # Fallback

            # Calculate line height (font size + small spacing)
            if hasattr(font, 'size'):
                line_height = font.size + 2
            else:
                # For BDF fonts, estimate height
                line_height = 8 if use_small else 10

            # Check if all lines fit within available width
            max_line_width = max(len(line) * avg_char_width for line in lines)
            if max_line_width > available_text_width:
                continue  # This font is too big for the width

            # Calculate total height needed
            total_height = num_lines * line_height

            # If this font fits better (larger font that still fits), use it
            if best_font is None or line_height > best_line_height:
                best_font = font
                best_line_height = line_height
                best_total_height = total_height
                best_use_small = use_small

        # If no font fits, use the smallest available
        if best_font is None:
            best_font = self.display_manager.extra_small_font
            best_use_small = True
            best_line_height = 8
            best_total_height = num_lines * best_line_height

        # Ensure total height doesn't exceed available height
        if best_total_height > available_text_height:
            # If text is too tall, reduce line height proportionally
            scale_factor = available_text_height / best_total_height
            best_line_height = int(best_line_height * scale_factor)
            best_total_height = best_line_height * num_lines

        # Calculate starting Y position to center vertically
        start_y = (height - best_total_height) // 2

        return {
            'font': best_font,
            'line_height': best_line_height,
            'total_text_height': best_total_height,
            'start_y': start_y,
            'use_small_font': best_use_small
        }
    
    def _draw_olympics_rings_programmatic(self, width: int, height: int) -> Image.Image:
        """
        Draw the Olympic rings programmatically as a fallback.
        
        Args:
            width: Width of the logo area
            height: Height of the logo area
            
        Returns:
            PIL Image with transparent background
        """
        # Create image with transparent background
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Olympic ring colors (from top to bottom)
        ring_colors = [
            (0, 129, 200),    # Blue
            (0, 0, 0),        # Black
            (255, 20, 24),    # Red
            (255, 195, 0),    # Yellow
            (0, 158, 96)      # Green
        ]
        
        # Calculate ring size and positions
        ring_radius = min(width, height) // 6
        center_x = width // 2
        center_y = height // 2
        
        # Draw rings in Olympic pattern (top row: 3, bottom row: 2)
        # Top row
        top_y = center_y - ring_radius
        for i, color in enumerate(ring_colors[:3]):
            x = center_x - ring_radius + (i * ring_radius * 1.5)
            y = top_y
            # Draw ring (circle outline)
            bbox = [x - ring_radius, y - ring_radius, x + ring_radius, y + ring_radius]
            draw.ellipse(bbox, outline=color, width=max(1, ring_radius // 8))
        
        # Bottom row
        bottom_y = center_y + ring_radius
        for i, color in enumerate(ring_colors[3:]):
            x = center_x + (i * ring_radius * 1.5)
            y = bottom_y
            bbox = [x - ring_radius, y - ring_radius, x + ring_radius, y + ring_radius]
            draw.ellipse(bbox, outline=color, width=max(1, ring_radius // 8))
        
        return img
    
    def _get_logo_image(self, width: int, height: int) -> Optional[Image.Image]:
        """
        Get Olympics logo image at specified dimensions.
        Preserves aspect ratio and fits within the given dimensions.
        
        Args:
            width: Maximum width in pixels
            height: Maximum height in pixels
            
        Returns:
            PIL Image scaled to fit within dimensions while preserving aspect ratio
        """
        if self.logo_image:
            # Calculate scaling to fit within dimensions while preserving aspect ratio
            img_width, img_height = self.logo_image.size
            width_ratio = width / img_width
            height_ratio = height / img_height
            scale_ratio = min(width_ratio, height_ratio)  # Use smaller ratio to fit both dimensions
            
            # Calculate new dimensions
            new_width = int(img_width * scale_ratio)
            new_height = int(img_height * scale_ratio)
            
            # Resize image preserving aspect ratio
            try:
                # Try new PIL API first
                resized = self.logo_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            except AttributeError:
                # Fall back to old PIL API
                resized = self.logo_image.resize((new_width, new_height), Image.LANCZOS)
            
            # If the image has transparency, ensure it's RGBA
            if resized.mode != 'RGBA' and self.logo_image.mode == 'RGBA':
                # Convert to RGBA if original was RGBA
                resized = resized.convert('RGBA')
            
            return resized
        else:
            # Draw programmatically with new dimensions
            return self._draw_olympics_rings_programmatic(width, height)
    
    def update(self) -> None:
        """
        Update countdown calculation.
        
        Called periodically to recalculate days until Olympics.
        """
        try:
            days, is_active, olympics_info, countdown_type = self._calculate_days_until()
            self.days_until = days
            self.is_olympics_active = is_active
            self.current_olympics = olympics_info
            self.countdown_type = countdown_type
            
            # Only log when the day changes
            today = date.today()
            if self.last_calculated_date != today:
                if olympics_info:
                    if is_active:
                        self.logger.info(f"Olympics {olympics_info['type']} {olympics_info['location']} is active. Days until closing: {days}")
                    else:
                        self.logger.info(f"Days until {olympics_info['type']} Olympics {olympics_info['location']} opening: {days}")
                else:
                    self.logger.warning("No upcoming Olympics found")
                self.last_calculated_date = today
                
        except Exception as e:
            self.logger.error(f"Error updating countdown: {e}")
    
    def display(self, force_clear: bool = False) -> None:
        """
        Display the Olympics countdown with split-screen layout.
        Logo on left, stacked text on right.
        
        Args:
            force_clear: If True, clear display before rendering
        """
        try:
            # Ensure update() has been called
            if not hasattr(self, 'days_until'):
                self.update()
            
            # Get display dimensions
            width = self.display_manager.width
            height = self.display_manager.height
            
            # Determine text to display
            if not self.current_olympics:
                message = "NO OLYMPICS FOUND"
                lines = ["NO OLYMPICS", "FOUND"]
            elif self.is_olympics_active:
                # Olympics is happening - countdown to closing
                if self.days_until == 0:
                    message = "OLYMPICS CLOSING"
                    lines = ["OLYMPICS", "CLOSING", "TODAY"]
                else:
                    olympics_type = self.current_olympics['type'].upper()
                    message = f"{self.days_until} DAYS UNTIL CLOSING"
                    lines = [
                        f"{self.days_until}",
                        "DAYS UNTIL",
                        "CLOSING"
                    ]
            else:
                # Countdown to opening
                olympics_type = self.current_olympics['type'].upper()
                location = self.current_olympics['location']
                
                if self.days_until == 0:
                    message = "OLYMPICS OPENING TODAY"
                    lines = ["OLYMPICS", "OPENING", "TODAY"]
                else:
                    # Shorten location name if too long
                    if len(location) > 12:
                        location = location.split('-')[0]  # Use first part if hyphenated
                    if len(location) > 12:
                        location = location[:10] + ".."
                    
                    message = f"{self.days_until} DAYS UNTIL {olympics_type} OLYMPICS"
                    lines = [
                        f"{self.days_until}",
                        "DAYS UNTIL",
                        f"{olympics_type}",
                        "OLYMPICS"
                    ]
            
            # Check if we need to redraw (prevent blinking)
            # Only redraw if the message changed or force_clear is True
            if not force_clear and self.last_displayed_message == message:
                return  # No change, skip redraw
            
            # Clear display
            self.display_manager.clear()
            
            # Split display in half: logo on left, text on right
            left_half_width = width // 2
            right_half_width = width - left_half_width
            right_half_x = left_half_width
            
            # Calculate logo dimensions (use most of left half, leave small margin)
            logo_margin = 2
            logo_width = left_half_width - (2 * logo_margin)
            logo_height = height - (2 * logo_margin)
            logo_x = logo_margin
            logo_y = logo_margin
            
            # Get logo image
            logo_img = self._get_logo_image(logo_width, logo_height)
            
            # Draw logo on left side
            if logo_img:
                # Paste logo onto display (handle RGBA with alpha channel)
                if logo_img.mode == 'RGBA':
                    self.display_manager.image.paste(logo_img, (logo_x, logo_y), logo_img)
                else:
                    self.display_manager.image.paste(logo_img, (logo_x, logo_y))
            
            # Calculate optimal text layout based on display size
            layout = self._calculate_text_layout(width, height, lines)

            # Draw each line of text, centered horizontally in right half
            for i, line in enumerate(lines):
                text_y = layout['start_y'] + (i * layout['line_height'])
                # Calculate center point of right half for centering
                right_half_center_x = right_half_x + (right_half_width // 2)

                # Use the calculated font
                if layout['font'] == self.display_manager.extra_small_font:
                    # For extra small font, we need to handle it specially since draw_text doesn't support it directly
                    # We'll use the font parameter
                    self.display_manager.draw_text(
                        line,
                        x=right_half_center_x,
                        y=text_y,
                        color=self.text_color,
                        font=layout['font'],
                        centered=True
                    )
                else:
                    # Use the small_font parameter for regular/small fonts
                    self.display_manager.draw_text(
                        line,
                        x=right_half_center_x,
                        y=text_y,
                        color=self.text_color,
                        small_font=layout['use_small_font'],
                        centered=True
                    )
            
            # Update the physical display
            self.display_manager.update_display()
            
            # Track what we displayed to prevent unnecessary redraws
            self.last_displayed_message = message
            self.logger.debug(f"Displayed: {message}")
            
        except Exception as e:
            self.logger.error(f"Error displaying countdown: {e}", exc_info=True)
            # Show error message on display
            try:
                self.display_manager.clear()
                self.display_manager.draw_text(
                    "Countdown Error",
                    x=5, y=15,
                    color=(255, 0, 0)
                )
                self.display_manager.update_display()
            except:
                pass  # If display fails, don't crash
    
    def validate_config(self) -> bool:
        """Validate plugin configuration."""
        # Call parent validation first
        if not super().validate_config():
            return False
        
        # Validate colors
        if not isinstance(self.text_color, tuple) or len(self.text_color) != 3:
            self.logger.error("Invalid text_color: must be RGB tuple")
            return False
        try:
            # Convert to integers and validate range
            color_ints = [int(c) for c in self.text_color]
            if not all(0 <= c <= 255 for c in color_ints):
                self.logger.error("Invalid text_color: values must be 0-255")
                return False
        except (ValueError, TypeError):
            self.logger.error("Invalid text_color: values must be numeric")
            return False
        
        # Validate logo_size if provided
        if self.logo_size is not None:
            if not isinstance(self.logo_size, (int, float)) or self.logo_size <= 0:
                self.logger.error("logo_size must be a positive number")
                return False
        
        return True
    
    def get_info(self) -> Dict[str, Any]:
        """Return plugin info for web UI."""
        info = super().get_info()
        info.update({
            'days_until': getattr(self, 'days_until', None),
            'is_olympics_active': getattr(self, 'is_olympics_active', False),
            'current_olympics': getattr(self, 'current_olympics', None),
            'countdown_type': getattr(self, 'countdown_type', 'opening'),
            'text_color': self.text_color,
            'logo_size': self.logo_size
        })
        return info

