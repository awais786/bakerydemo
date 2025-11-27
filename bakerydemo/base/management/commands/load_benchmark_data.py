import random
from datetime import date, time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import lorem_ipsum
from django.utils.text import slugify
from taggit.models import Tag
from wagtail.images.models import Image
from wagtail.models import Site
from wagtail.rich_text import RichText
from willow.image import Image as WillowImage

from bakerydemo.base.models import HomePage, Person
from bakerydemo.blog.models import BlogIndexPage, BlogPage, BlogPersonRelationship
from bakerydemo.breads.models import BreadIngredient, BreadPage, BreadsIndexPage, BreadType, Country
from bakerydemo.locations.models import LocationOperatingHours, LocationPage, LocationsIndexPage

FIXTURE_MEDIA_DIR = Path(settings.PROJECT_DIR) / "base/fixtures/media/original_images"

# Benchmark configuration constants
STREAMFIELD_BLOCKS = 100
STREAMFIELD_NESTING = 10
INLINE_PANEL_ITEMS = 100
RICH_TEXT_PARAGRAPHS = 100
REVISIONS_PER_PAGE = 5

# Page count constants
BLOG_PAGES = 100
BREAD_PAGES = 100
LOCATION_PAGES = 50


class Command(BaseCommand):
    help = 'Load benchmark data for performance testing using existing content types'

    def handle(self, *args, **options):
        blog_count = BLOG_PAGES
        bread_count = BREAD_PAGES
        location_count = LOCATION_PAGES

        self.stdout.write('Starting benchmark data generation.')
        self.stdout.write(
            f'Target: {blog_count} blog, {bread_count} bread, {location_count} location pages'
        )
        self.stdout.write(f'Revisions per page: {REVISIONS_PER_PAGE}')
        self.stdout.write(f'StreamField blocks per page: {STREAMFIELD_BLOCKS}')
        self.stdout.write(f'StreamField nesting depth: {STREAMFIELD_NESTING}')
        self.stdout.write(f'InlinePanel items per page: {INLINE_PANEL_ITEMS}')
        self.stdout.write(f'Rich text paragraphs: {RICH_TEXT_PARAGRAPHS}')

        # Get the home page
        try:
            home_page = Site.objects.get(is_default_site=True).root_page
        except (Site.DoesNotExist, Site.MultipleObjectsReturned) as e:
            self.stdout.write(self.style.ERROR(f'Could not find home page: {e}. Please set up the site first.'))
            return

        # Create blog pages
        if blog_count > 0:
            self.stdout.write('Creating blog pages...')
            created = self.create_blog_pages(home_page, blog_count)
            self.stdout.write(f'Created {created} new blog pages')

        # Create bread pages
        if bread_count > 0:
            self.stdout.write('Creating bread pages...')
            created = self.create_bread_pages(home_page, bread_count)
            self.stdout.write(f'Created {created} new bread pages')

        # Create location pages
        if location_count > 0:
            self.stdout.write('Creating location pages...')
            created = self.create_location_pages(home_page, location_count)
            self.stdout.write(f'Created {created} new location pages')

        self.stdout.write('Benchmark data generation complete!')

    def _get_images_cache(self):
        """Cache all available images to avoid repeated queries."""
        if not hasattr(self, '_images_cache'):
            self._images_cache = list(Image.objects.all())
        return self._images_cache

    def get_random_image(self):
        """
        Get a random image from cached images.
        Returns None if no images are available.
        """
        images = self._get_images_cache()
        if images:
            return random.choice(images)
        return None

    def generate_nested_block_quote(self, depth, max_depth):
        """
        Generate a nested BlockQuote structure with ThemeSettingsBlock.
        Creates nesting by recursively nesting settings blocks.
        """
        if depth >= max_depth:
            # At max depth, return a simple block quote
            return {
                'text': lorem_ipsum.paragraph(),
                'attribute_name': lorem_ipsum.words(2, common=False),
                'settings': {
                    'theme': random.choice(['default', 'highlight']),
                    'text_size': random.choice(['default', 'large'])
                }
            }

        nested_text = lorem_ipsum.paragraph()
        for _ in range(depth):
            nested_text = f"[Level {depth}] {nested_text}"

        return {
            'text': nested_text,
            'attribute_name': lorem_ipsum.words(2, common=False),
            'settings': {
                'theme': random.choice(['default', 'highlight']),
                'text_size': random.choice(['default', 'large'])
            }
        }

    def _create_heading_block(self):
        """Create a heading block."""
        return ('heading_block', {
            'heading_text': lorem_ipsum.words(random.randint(3, 8), common=False),
            'size': random.choice(['h2', 'h3', 'h4', ''])
        })

    def _create_paragraph_block(self, min_paragraphs=1, max_paragraphs=3):
        """Create a paragraph block."""
        paragraph_text = '\n'.join(lorem_ipsum.paragraphs(random.randint(min_paragraphs, max_paragraphs)))
        return ('paragraph_block', RichText(paragraph_text))

    def _create_block_quote(self, block_quote_index, nest_interval, max_nesting):
        """Create a block quote, nested if appropriate.
        
        Args:
            block_quote_index: The 0-based index of this block quote (not the overall position)
            nest_interval: Nest every Nth block quote (None to disable nesting)
            max_nesting: Maximum nesting depth
        """
        if nest_interval and block_quote_index > 0 and block_quote_index % nest_interval == 0:
            nesting_level = min(block_quote_index // nest_interval, max_nesting)
            return ('block_quote', self.generate_nested_block_quote(nesting_level, max_nesting))
        else:
            return ('block_quote', {
                'text': lorem_ipsum.paragraph(),
                'attribute_name': lorem_ipsum.words(2, common=False),
                'settings': {
                    'theme': random.choice(['default', 'highlight']),
                    'text_size': random.choice(['default', 'large'])
                }
            })

    def generate_streamfield(self, num_blocks, num_paragraphs=0, max_nesting=0):
        """
        Generate StreamField data with specified number of blocks.
        Supports up to 100 blocks with mix of different block types.
        Supports nesting up to 10 levels deep.
        
        Ensures minimum variety: at least 10% headings and 10% block quotes
        (unless num_blocks is very small), while meeting paragraph requirements.
        """
        blocks = []
        paragraph_count = 0
        block_quote_count = 0
        heading_count = 0

        # Calculate minimum variety to ensure mix of block types
        # Reserve at least 10% for headings and 10% for block quotes (minimum 1 each)
        min_headings = max(1, int(num_blocks * 0.1))
        min_block_quotes = max(1, int(num_blocks * 0.1))
        # Calculate how many paragraphs we can create while maintaining variety
        max_paragraphs_with_variety = num_blocks - min_headings - min_block_quotes
        # Target paragraphs: use requested amount, but cap at available slots
        target_paragraphs = min(num_paragraphs, max_paragraphs_with_variety) if num_paragraphs > 0 else max_paragraphs_with_variety

        # Calculate nesting interval if nesting is enabled
        # Use actual minimum block quotes for accurate nesting calculation
        nest_interval = None
        if max_nesting > 0 and min_block_quotes > 0:
            # Use max(1, ...) to ensure we never divide by 0
            nest_interval = max(1, min_block_quotes // max(1, max_nesting))

        for i in range(num_blocks):
            # Cycle through 4 block types: 0=heading, 1=block_quote, 2=heading, 3=paragraph
            block_type = i % 4

            # Priority 1: Ensure minimum block quotes for variety and nesting
            if block_type == 1 and block_quote_count < min_block_quotes:
                blocks.append(self._create_block_quote(block_quote_count, nest_interval, max_nesting))
                block_quote_count += 1
            # Priority 2: Ensure minimum headings for variety
            elif block_type in (0, 2) and heading_count < min_headings:
                blocks.append(self._create_heading_block())
                heading_count += 1
            # Priority 3: Create paragraphs to meet requirement
            elif num_paragraphs > 0 and paragraph_count < target_paragraphs:
                blocks.append(self._create_paragraph_block(min_paragraphs=2, max_paragraphs=5))
                paragraph_count += 1
            # Priority 4: Follow natural cycle for remaining blocks
            elif block_type == 3:  # paragraph slot
                blocks.append(self._create_paragraph_block())
                paragraph_count += 1
            elif block_type == 1:  # block_quote slot
                blocks.append(self._create_block_quote(block_quote_count, nest_interval, max_nesting))
                block_quote_count += 1
            else:  # block_type in (0, 2) - heading slot
                blocks.append(self._create_heading_block())
                heading_count += 1

        return blocks

    def _publish_page_with_revisions(self, page, revisions):
        """Common helper to publish a page and create additional revisions."""
        # Store original introduction before any modifications
        original_introduction = page.introduction
        
        revision = page.save_revision()
        revision.publish()
        page.refresh_from_db()

        # Create additional revisions (these will be drafts)
        for rev_num in range(revisions - 1):
            page.introduction = f"[Revision {rev_num + 2}] " + original_introduction
            page.save_revision()
        
        # Restore original introduction so page object reflects published state
        page.introduction = original_introduction
        page.refresh_from_db()

    def _find_max_page_number(self, model, title_prefix, extract_number_func):
        """Generic helper to find the highest existing page number."""
        existing_pages = model.objects.filter(title__startswith=title_prefix)
        max_existing = 0
        for page in existing_pages:
            try:
                num = extract_number_func(page.title)
                if num is not None:
                    max_existing = max(max_existing, num)
            except (ValueError, IndexError, AttributeError):
                pass
        return max_existing

    def create_blog_pages(self, home_page, count):
        """Create blog pages using existing BlogPage model"""
        revisions = REVISIONS_PER_PAGE
        streamfield_blocks = STREAMFIELD_BLOCKS
        inline_panel_items = INLINE_PANEL_ITEMS
        rich_text_paragraphs = RICH_TEXT_PARAGRAPHS
        streamfield_nesting = STREAMFIELD_NESTING
        blog_index = BlogIndexPage.objects.filter(slug='blog').first()

        if not blog_index:
            self.stdout.write(self.style.WARNING('  Blog index not found. Skipping blog pages.'))
            return 0

        # Get or create people for relationships
        people = list(Person.objects.all())
        if not people and inline_panel_items > 0:
            self.stdout.write(self.style.WARNING('  No Person objects found. Creating sample people...'))
            people_to_create = []
            for i in range(max(10, inline_panel_items)):
                people_to_create.append(Person(
                    first_name=lorem_ipsum.words(1, common=False),
                    last_name=lorem_ipsum.words(1, common=False),
                    job_title=lorem_ipsum.words(2, common=False),
                ))
            Person.objects.bulk_create(people_to_create)
            people = list(Person.objects.all())

        # Find the highest existing blog post number
        def extract_blog_number(title):
            return int(title.split()[-1])

        start_number = self._find_max_page_number(BlogPage, 'Blog Post', extract_blog_number) + 1
        created_count = 0

        # Get or create some tags
        tag_names = ['baking', 'bread', 'recipe', 'cooking', 'food', 'bakery', 'yeast', 'dough', 'pastry', 'dessert']
        tags = []
        for tag_name in tag_names:
            tag, _ = Tag.objects.get_or_create(name=tag_name)
            tags.append(tag)

        # Generate StreamField body once and reuse for all blog pages
        body = self.generate_streamfield(streamfield_blocks, rich_text_paragraphs,
                                         max_nesting=streamfield_nesting)

        for i in range(count):
            page_number = start_number + i
            title = f"Blog Post {page_number}"
            slug = slugify(title)

            # Double-check it doesn't exist (safety check)
            if BlogPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():

                # Get random image
                selected_image = self.get_random_image()

                page = BlogPage(
                    title=title,
                    slug=slug,
                    subtitle=lorem_ipsum.words(random.randint(5, 12), common=False),
                    introduction=lorem_ipsum.paragraph(),
                    body=body,
                    image=selected_image,
                    date_published=date.today(),
                )
                blog_index.add_child(instance=page)
                # add_child() already saves the page, but we need to refresh to get the ID
                page.refresh_from_db()

                # Create BlogPersonRelationship items (InlinePanel equivalent)
                if inline_panel_items > 0 and people:
                    selected_people = random.sample(people, min(inline_panel_items, len(people)))
                    relationships = [
                        BlogPersonRelationship(page=page, person=person)
                        for person in selected_people
                    ]
                    BlogPersonRelationship.objects.bulk_create(relationships)
                    # Save page after adding relationships
                    page.save()

                # Add tags
                if tags:
                    selected_tags = random.sample(tags, min(random.randint(2, 5), len(tags)))
                    page.tags.add(*selected_tags)
                    page.save()

                # Create initial revision and publish, then create additional revisions
                self._publish_page_with_revisions(page, revisions)

                created_count += 1

        return created_count

    def create_bread_pages(self, home_page, count):
        """Create bread pages using existing BreadPage model"""
        revisions = REVISIONS_PER_PAGE
        streamfield_blocks = STREAMFIELD_BLOCKS
        streamfield_nesting = STREAMFIELD_NESTING
        breads_index = BreadsIndexPage.objects.filter(slug='breads').first()

        if not breads_index:
            self.stdout.write(self.style.WARNING('  Breads index not found. Skipping bread pages.'))
            return 0

        bread_type_names = ['Sourdough', 'Baguette', 'Ciabatta', 'Rye', 'Whole Wheat',
                            'Multigrain', 'Pumpernickel', 'Focaccia', 'Challah', 'Brioche',
                            'Naan', 'Pita', 'Cornbread', 'Flatbread', 'Tortilla']

        country_names = ['France', 'Italy', 'Germany', 'United States', 'United Kingdom',
                         'Spain', 'Greece', 'Turkey', 'India', 'Mexico', 'Canada', 'Australia']

        # Get or create bread types
        bread_types = []
        for name in bread_type_names:
            bread_type, _ = BreadType.objects.get_or_create(title=name)
            bread_types.append(bread_type)

        # Get or create countries
        countries = []
        for name in country_names:
            country, _ = Country.objects.get_or_create(title=name)
            countries.append(country)

        # Get or create some ingredients
        ingredient_names = ['Flour', 'Water', 'Yeast', 'Salt', 'Sugar', 'Olive Oil',
                            'Butter', 'Eggs', 'Milk', 'Honey', 'Seeds', 'Nuts']
        ingredients = []
        for name in ingredient_names:
            ingredient, _ = BreadIngredient.objects.get_or_create(name=name)
            ingredients.append(ingredient)

        # Find the highest existing bread page number
        def extract_bread_number(title):
            if '#' in title:
                parts = title.split('#')
                if len(parts) > 1:
                    return int(parts[-1].strip())
            return None

        start_number = self._find_max_page_number(BreadPage, '', extract_bread_number) + 1
        created_count = 0

        # Generate StreamField body once and reuse for all bread pages
        body = self.generate_streamfield(streamfield_blocks, max_nesting=streamfield_nesting)

        for i in range(count):
            page_number = start_number + i
            bread_type_name = random.choice(bread_type_names)
            title = f"{bread_type_name} #{page_number}"
            slug = slugify(title)

            if BreadPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():

                # Select random bread_type, origin, ingredients, and image
                selected_bread_type = random.choice(bread_types)
                selected_origin = random.choice(countries) if countries else None
                selected_ingredients = random.sample(ingredients,
                                                     min(random.randint(3, 8), len(ingredients))) if ingredients else []
                selected_image = self.get_random_image()

                page = BreadPage(
                    title=title,
                    slug=slug,
                    introduction=lorem_ipsum.paragraph(),
                    body=body,
                    bread_type=selected_bread_type,
                    origin=selected_origin,
                    image=selected_image,
                )
                breads_index.add_child(instance=page)
                # add_child() already saves the page, but we need to refresh to get the ID
                page.refresh_from_db()

                # Set ingredients (many-to-many relationship)
                if selected_ingredients:
                    page.ingredients.set(selected_ingredients)
                    # Save page after setting ingredients
                    page.save()

                # Create initial revision and publish, then create additional revisions
                self._publish_page_with_revisions(page, revisions)

                created_count += 1

        return created_count

    def _find_max_location_page_number(self):
        """Find the highest existing location page number."""

        def extract_location_number(title):
            if '#' in title:
                parts = title.split('#')
                if len(parts) > 1:
                    return int(parts[-1].strip())
            return None

        return self._find_max_page_number(LocationPage, '', extract_location_number)

    def _generate_location_address(self, city):
        """Generate a multi-line address for a location."""
        street_number = random.randint(1, 999)
        street_name = random.choice(['Main Street', 'Oak Avenue', 'Park Road', 'High Street', 'Church Lane'])
        country = random.choice(['Iceland', 'United States', 'United Kingdom', 'France', 'Germany'])
        return f"{street_number} {street_name},\r\n{city},\r\n{country}"

    def _generate_lat_long(self):
        """Generate a latitude/longitude string with space after comma."""
        lat = random.uniform(-90, 90)
        lng = random.uniform(-180, 180)
        return f"{lat:.6f}, {lng:.6f}"

    def _create_operating_hours(self, page):
        """Create LocationOperatingHours items for a location page.
        Creates one entry per day of the week (7 entries total).
        Uses consistent business hours for weekdays, with optional weekend closure.
        """
        days = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

        # Standard business hours (9am-5pm) for weekdays
        weekday_open = time(9, 0)
        weekday_close = time(17, 0)

        # Weekend hours might be shorter or closed
        weekend_open = time(10, 0)
        weekend_close = time(16, 0)

        # Randomly decide if location is closed on weekends
        closed_on_weekends = random.random() < 0.3

        operating_hours = []
        for day in days:
            is_weekend = day in ['SAT', 'SUN']
            is_closed = is_weekend and closed_on_weekends

            if is_closed:
                # When closed, set both times to None or use a default
                opening_time = time(0, 0)
                closing_time = time(0, 0)
            elif is_weekend:
                opening_time = weekend_open
                closing_time = weekend_close
            else:
                opening_time = weekday_open
                closing_time = weekday_close

            operating_hours.append(LocationOperatingHours(
                location=page,
                day=day,
                opening_time=opening_time,
                closing_time=closing_time,
                closed=is_closed
            ))

        LocationOperatingHours.objects.bulk_create(operating_hours)
        page.save()

    def create_location_pages(self, home_page, count):
        """Create location pages using existing LocationPage model"""
        revisions = REVISIONS_PER_PAGE
        streamfield_blocks = STREAMFIELD_BLOCKS
        streamfield_nesting = STREAMFIELD_NESTING
        locations_index = LocationsIndexPage.objects.filter(slug='locations').first()

        if not locations_index:
            self.stdout.write(self.style.WARNING('  Locations index not found. Skipping location pages.'))
            return 0

        cities = ['New York', 'London', 'Paris', 'Tokyo', 'Sydney', 'Berlin',
                  'Toronto', 'Mumbai', 'Singapore', 'Dubai', 'Barcelona', 'Amsterdam',
                  'Rome', 'Madrid', 'Seoul', 'San Francisco', 'Chicago', 'Boston']

        start_number = self._find_max_location_page_number() + 1
        created_count = 0

        # Generate StreamField body once and reuse for all location pages
        body = self.generate_streamfield(streamfield_blocks, max_nesting=streamfield_nesting)

        for i in range(count):
            city = random.choice(cities)
            page_number = start_number + i
            title = f"{city} Location #{page_number}"
            slug = slugify(title)

            if LocationPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                selected_image = self.get_random_image()
                address = self._generate_location_address(city)
                lat_long = self._generate_lat_long()

                page = LocationPage(
                    title=title,
                    slug=slug,
                    introduction=lorem_ipsum.paragraph(),
                    body=body,
                    address=address,
                    lat_long=lat_long,
                    image=selected_image,
                )
                locations_index.add_child(instance=page)
                page.refresh_from_db()

                # Create operating hours (7 entries - one per day)
                self._create_operating_hours(page)

                # Create initial revision and publish, then create additional revisions
                self._publish_page_with_revisions(page, revisions)

                created_count += 1

        return created_count
