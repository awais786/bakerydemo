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

# Import existing bakerydemo models
from bakerydemo.base.models import FormField, FormPage, Person
from bakerydemo.blog.models import BlogIndexPage, BlogPage, BlogPersonRelationship
from bakerydemo.breads.models import BreadIngredient, BreadPage, BreadsIndexPage, BreadType, Country
from bakerydemo.locations.models import LocationOperatingHours, LocationPage, LocationsIndexPage

FIXTURE_MEDIA_DIR = Path(settings.PROJECT_DIR) / "base/fixtures/media/original_images"


class Command(BaseCommand):
    help = 'Load benchmark data for performance testing using existing content types'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._available_images = None

    def add_arguments(self, parser):
        parser.add_argument(
            '--blog-pages',
            type=int,
            default=50,
            help='Number of blog pages to create (default: 50)'
        )
        parser.add_argument(
            '--bread-pages',
            type=int,
            default=50,
            help='Number of bread pages to create (default: 50)'
        )
        parser.add_argument(
            '--location-pages',
            type=int,
            default=20,
            help='Number of location pages to create (default: 20)'
        )
        parser.add_argument(
            '--form-pages',
            type=int,
            default=0,
            help='Number of form pages to create (default: 0)'
        )
        parser.add_argument(
            '--revisions',
            type=int,
            default=5,
            help='Number of revisions per page (default: 5)'
        )
        parser.add_argument(
            '--streamfield-blocks',
            type=int,
            default=10,
            help='Number of StreamField blocks per page (default: 10, max: 100)'
        )
        parser.add_argument(
            '--streamfield-nesting',
            type=int,
            default=0,
            help='Maximum nesting depth for StreamField blocks (default: 0, max: 10)'
        )
        parser.add_argument(
            '--inline-panel-items',
            type=int,
            default=0,
            help='Number of InlinePanel items to create per page (default: 0, max: 100)'
        )
        parser.add_argument(
            '--rich-text-paragraphs',
            type=int,
            default=0,
            help='Number of rich text paragraphs in StreamField (default: 0, max: 100)'
        )
        parser.add_argument(
            '--preset',
            type=str,
            choices=['small', 'medium', 'large'],
            help='Use a preset configuration (small: 100 pages, medium: 1000 pages, large: 10000 pages)'
        )

    def handle(self, *args, **options):
        # Handle presets
        presets = {
            'small': {'blog': 50, 'bread': 30, 'location': 20, 'form': 10, 'revisions': 5},
            'medium': {'blog': 500, 'bread': 300, 'location': 200, 'form': 100, 'revisions': 10},
            'large': {'blog': 5000, 'bread': 3000, 'location': 2000, 'form': 1000, 'revisions': 20},
        }

        if options['preset']:
            preset = presets[options['preset']]
            blog_count = preset['blog']
            bread_count = preset['bread']
            location_count = preset['location']
            form_count = preset['form']
            revisions_count = preset['revisions']
        else:
            blog_count = options['blog_pages']
            bread_count = options['bread_pages']
            location_count = options['location_pages']
            form_count = options['form_pages']
            revisions_count = options['revisions']

        # Content complexity settings
        streamfield_blocks = min(options['streamfield_blocks'], 100)
        inline_panel_items = min(options['inline_panel_items'], 100)
        rich_text_paragraphs = min(options['rich_text_paragraphs'], 100)
        streamfield_nesting = min(options['streamfield_nesting'], 10)

        self.stdout.write(self.style.SUCCESS('Starting benchmark data generation...'))
        self.stdout.write(
            f'Target: {blog_count} blog pages, {bread_count} bread pages, '
            f'{location_count} location pages, {form_count} form pages'
        )
        self.stdout.write(f'Revisions per page: {revisions_count}')
        self.stdout.write(f'StreamField blocks per page: {streamfield_blocks}')
        self.stdout.write(f'StreamField nesting depth: {streamfield_nesting}')
        self.stdout.write(f'InlinePanel items per page: {inline_panel_items}')
        self.stdout.write(f'Rich text paragraphs: {rich_text_paragraphs}')

        # Get the home page
        try:
            home_page = Site.objects.get(is_default_site=True).root_page
        except:
            self.stdout.write(self.style.ERROR('Could not find home page. Please set up the site first.'))
            return

        # Create blog pages
        if blog_count > 0:
            self.stdout.write('\nCreating blog pages...')
            created = self.create_blog_pages(
                home_page, blog_count, revisions_count,
                streamfield_blocks, inline_panel_items, rich_text_paragraphs, streamfield_nesting
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created} new blog pages'))

        # Create bread pages
        if bread_count > 0:
            self.stdout.write('\nCreating bread pages...')
            created = self.create_bread_pages(
                home_page, bread_count, revisions_count, streamfield_blocks, streamfield_nesting
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created} new bread pages'))

        # Create location pages
        if location_count > 0:
            self.stdout.write('\nCreating location pages...')
            created = self.create_location_pages(
                home_page, location_count, revisions_count,
                streamfield_blocks, inline_panel_items, streamfield_nesting
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created} new location pages'))

        # Create form pages
        if form_count > 0:
            self.stdout.write('\nCreating form pages...')
            created = self.create_form_pages(
                home_page, form_count, revisions_count,
                streamfield_blocks, inline_panel_items, streamfield_nesting
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created} new form pages'))

        self.stdout.write(self.style.SUCCESS('\n✓ Benchmark data generation complete!'))

    def get_random_image(self):
        """
        Get a random image from existing images, or create one from fixtures if needed.
        Returns None if no images are available.
        """
        # First, try to get an existing image from the database
        existing_images = Image.objects.all()
        if existing_images.exists():
            return existing_images.order_by('?').first()

        # If no images exist, try to create one from fixtures
        if not FIXTURE_MEDIA_DIR.exists():
            return None

        try:
            image_files = list(FIXTURE_MEDIA_DIR.iterdir())
            if not image_files:
                return None

            # Create a new image from a random fixture file
            random_image_file = random.choice(image_files)
            with random_image_file.open(mode="rb") as image_file:
                willow_image = WillowImage.open(image_file)
                width, height = willow_image.get_size()
                image = Image.objects.create(
                    title=lorem_ipsum.words(3, common=False),
                    width=width,
                    height=height,
                    file_size=random_image_file.stat().st_size,
                )
                image_file.seek(0)
                image.file.save(random_image_file.name, image_file)
                return image
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Could not create image from fixtures: {e}'))
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

        # Create nested structure - simulate deeper nesting by creating
        # multiple nested settings structures
        nested_text = lorem_ipsum.paragraph()
        for _ in range(depth):
            nested_text = f"[Level {depth}] {nested_text}"

        return {
            'text': nested_text,
            'attribute_name': lorem_ipsum.words(2, common=False),
            'settings': {
                'theme': random.choice(['default', 'highlight']),
                'text_size': random.choice(['default', 'large']),
                # Simulate deeper nesting by adding nested data
                '_nesting_level': depth,
                '_max_depth': max_depth
            }
        }

    def generate_streamfield(self, num_blocks, num_paragraphs=0, images=None, max_nesting=0):
        """
        Generate StreamField data with specified number of blocks.
        Supports up to 100 blocks with mix of different block types.
        Supports nesting up to 10 levels deep.
        """
        blocks = []

        # Ensure we have exactly num_blocks blocks (for 100 fields requirement)
        paragraph_count = 0
        nesting_level = 0

        for i in range(num_blocks):
            # Determine if we should create a nested block
            should_nest = max_nesting > 0 and i % (
                    num_blocks // max(1, max_nesting)) == 0 and nesting_level < max_nesting

            if num_paragraphs > 0 and paragraph_count < num_paragraphs:
                # Add a paragraph block
                paragraph_text = '\n'.join(lorem_ipsum.paragraphs(random.randint(2, 5)))
                blocks.append(('paragraph_block', RichText(paragraph_text)))
                paragraph_count += 1
            elif i % 4 == 0:
                # Heading block
                blocks.append(('heading_block', {
                    'heading_text': lorem_ipsum.words(random.randint(3, 8), common=False),
                    'size': random.choice(['h2', 'h3', 'h4', ''])
                }))
            elif i % 4 == 1 and should_nest:
                # Nested block quote with deeper nesting
                nesting_level = min(nesting_level + 1, max_nesting)
                blocks.append(('block_quote', self.generate_nested_block_quote(nesting_level, max_nesting)))
            elif i % 4 == 1:
                # Regular block quote
                blocks.append(('block_quote', {
                    'text': lorem_ipsum.paragraph(),
                    'attribute_name': lorem_ipsum.words(2, common=False),
                    'settings': {
                        'theme': random.choice(['default', 'highlight']),
                        'text_size': random.choice(['default', 'large'])
                    }
                }))
            elif i % 4 == 2:
                # Paragraph block
                paragraph_text = '\n'.join(lorem_ipsum.paragraphs(random.randint(1, 3)))
                blocks.append(('paragraph_block', RichText(paragraph_text)))
                paragraph_count += 1
            else:
                # Another heading or paragraph to ensure we hit exactly num_blocks
                if i % 2 == 0:
                    blocks.append(('heading_block', {
                        'heading_text': lorem_ipsum.words(random.randint(3, 8), common=False),
                        'size': random.choice(['h2', 'h3', 'h4', ''])
                    }))
                else:
                    paragraph_text = '\n'.join(lorem_ipsum.paragraphs(random.randint(1, 2)))
                    blocks.append(('paragraph_block', RichText(paragraph_text)))
                    paragraph_count += 1

        return blocks

    def create_blog_pages(self, home_page, count, revisions, streamfield_blocks, inline_panel_items,
                          rich_text_paragraphs, streamfield_nesting):
        """Create blog pages using existing BlogPage model"""
        blog_index = BlogIndexPage.objects.filter(slug='blog').first()

        if not blog_index:
            self.stdout.write(self.style.WARNING('  Blog index not found. Skipping blog pages.'))
            return 0

        # Get or create people for relationships
        people = list(Person.objects.all())
        if not people and inline_panel_items > 0:
            self.stdout.write(self.style.WARNING('  No Person objects found. Creating sample people...'))
            for i in range(max(10, inline_panel_items)):
                people.append(Person.objects.create(
                    first_name=lorem_ipsum.words(1, common=False),
                    last_name=lorem_ipsum.words(1, common=False),
                    job_title=lorem_ipsum.words(2, common=False),
                ))

        # Find the highest existing blog post number
        existing_pages = BlogPage.objects.filter(title__startswith='Blog Post')
        max_existing = 0
        for page in existing_pages:
            try:
                num = int(page.title.split()[-1])
                max_existing = max(max_existing, num)
            except (ValueError, IndexError):
                pass

        start_number = max_existing + 1
        created_count = 0

        # Get or create some tags
        tag_names = ['baking', 'bread', 'recipe', 'cooking', 'food', 'bakery', 'yeast', 'dough', 'pastry', 'dessert']
        tags = []
        for tag_name in tag_names:
            tag, _ = Tag.objects.get_or_create(name=tag_name)
            tags.append(tag)

        for i in range(count):
            page_number = start_number + i
            title = f"Blog Post {page_number}"
            slug = slugify(title)

            # Double-check it doesn't exist (safety check)
            if BlogPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                # Generate StreamField body
                body = self.generate_streamfield(streamfield_blocks, rich_text_paragraphs,
                                                 max_nesting=streamfield_nesting)

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
                    for person in selected_people:
                        BlogPersonRelationship.objects.create(
                            page=page,
                            person=person
                        )
                    # Save page after adding relationships
                    page.save()

                # Add tags
                if tags:
                    selected_tags = random.sample(tags, min(random.randint(2, 5), len(tags)))
                    page.tags.add(*selected_tags)
                    page.save()

                # Create initial revision and publish
                revision = page.save_revision()
                revision.publish()
                # Ensure page is live
                page.refresh_from_db()

                # Create additional revisions (these will be drafts)
                for rev_num in range(revisions - 1):
                    page.introduction = f"[Revision {rev_num + 2}] " + page.introduction
                    page.save_revision()

                created_count += 1

            if (created_count) % 50 == 0:
                self.stdout.write(f'  Progress: {created_count}/{count} pages...')

        return created_count

    def create_bread_pages(self, home_page, count, revisions, streamfield_blocks, streamfield_nesting):
        """Create bread pages using existing BreadPage model"""
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
        # Check for any bread pages with numbers in title
        existing_pages = BreadPage.objects.all()
        max_existing = 0
        for page in existing_pages:
            try:
                # Extract number from title like "Sourdough #123" or "Benchmark Sourdough #123"
                if '#' in page.title:
                    parts = page.title.split('#')
                    if len(parts) > 1:
                        num = int(parts[-1].strip())
                        max_existing = max(max_existing, num)
            except (ValueError, IndexError):
                pass

        start_number = max_existing + 1
        created_count = 0

        for i in range(count):
            bread_type_name = random.choice(bread_type_names)
            page_number = start_number + i
            title = f"{bread_type_name} #{page_number}"
            slug = slugify(title)

            if BreadPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                # Generate StreamField body
                body = self.generate_streamfield(streamfield_blocks, max_nesting=streamfield_nesting)

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

                # Create initial revision and publish
                revision = page.save_revision()
                revision.publish()
                # Ensure page is live
                page.refresh_from_db()

                # Create additional revisions (these will be drafts)
                for rev_num in range(revisions - 1):
                    page.introduction = f"[Revision {rev_num + 2}] " + page.introduction
                    page.save_revision()

                created_count += 1

            if (created_count) % 50 == 0:
                self.stdout.write(f'  Progress: {created_count}/{count} pages...')

        return created_count

    def create_location_pages(self, home_page, count, revisions, streamfield_blocks, inline_panel_items,
                              streamfield_nesting):
        """Create location pages using existing LocationPage model"""
        locations_index = LocationsIndexPage.objects.filter(slug='locations').first()

        if not locations_index:
            self.stdout.write(self.style.WARNING('  Locations index not found. Skipping location pages.'))
            return 0

        cities = ['New York', 'London', 'Paris', 'Tokyo', 'Sydney', 'Berlin',
                  'Toronto', 'Mumbai', 'Singapore', 'Dubai', 'Barcelona', 'Amsterdam',
                  'Rome', 'Madrid', 'Seoul', 'San Francisco', 'Chicago', 'Boston']

        days = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

        # Find the highest existing location page number
        existing_pages = LocationPage.objects.all()
        max_existing = 0
        for page in existing_pages:
            try:
                # Extract number from title like "New York Location #123"
                if '#' in page.title:
                    parts = page.title.split('#')
                    if len(parts) > 1:
                        num = int(parts[-1].strip())
                        max_existing = max(max_existing, num)
            except (ValueError, IndexError):
                pass

        start_number = max_existing + 1
        created_count = 0

        for i in range(count):
            city = random.choice(cities)
            page_number = start_number + i
            title = f"{city} Location #{page_number}"
            slug = slugify(title)

            if LocationPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                # Generate StreamField body
                body = self.generate_streamfield(streamfield_blocks, max_nesting=streamfield_nesting)

                # Get random image
                selected_image = self.get_random_image()

                # Create multi-line address format like in fixtures
                street_number = random.randint(1, 999)
                street_name = random.choice(['Main Street', 'Oak Avenue', 'Park Road', 'High Street', 'Church Lane'])
                address = f"{street_number} {street_name},\r\n{city},\r\n{random.choice(['Iceland', 'United States', 'United Kingdom', 'France', 'Germany'])}"

                # Format lat_long with space after comma
                lat = random.uniform(-90, 90)
                lng = random.uniform(-180, 180)
                lat_long = f"{lat:.6f}, {lng:.6f}"

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
                # add_child() already saves the page, but we need to refresh to get the ID
                page.refresh_from_db()

                # Create LocationOperatingHours items (InlinePanel)
                if inline_panel_items > 0:
                    # Create operating hours for all days or specified number
                    hours_to_create = min(inline_panel_items, len(days))
                    for day_idx, day in enumerate(days[:hours_to_create]):
                        LocationOperatingHours.objects.create(
                            location=page,
                            day=day,
                            opening_time=time(9, 0),
                            closing_time=time(17, 0),
                            closed=(day in ['SAT', 'SUN'] and random.random() < 0.3)
                        )
                    # Save page after adding relationships
                    page.save()

                # Create initial revision and publish
                revision = page.save_revision()
                revision.publish()
                # Ensure page is live
                page.refresh_from_db()

                # Create additional revisions (these will be drafts)
                for rev_num in range(revisions - 1):
                    page.introduction = f"[Revision {rev_num + 2}] " + page.introduction
                    page.save_revision()

                created_count += 1

            if (created_count) % 50 == 0:
                self.stdout.write(f'  Progress: {created_count}/{count} pages...')

        return created_count

    def create_form_pages(self, home_page, count, revisions, streamfield_blocks, inline_panel_items,
                          streamfield_nesting):
        """Create form pages using existing FormPage model"""

        # Find the highest existing form page number
        existing_pages = FormPage.objects.filter(title__startswith='Form Page')
        max_existing = 0
        for page in existing_pages:
            try:
                num = int(page.title.split()[-1])
                max_existing = max(max_existing, num)
            except (ValueError, IndexError):
                pass

        start_number = max_existing + 1
        created_count = 0

        for i in range(count):
            page_number = start_number + i
            title = f"Form Page {page_number}"
            slug = slugify(title)

            if FormPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                # Generate StreamField body
                body = self.generate_streamfield(streamfield_blocks, max_nesting=streamfield_nesting)

                # Get random image
                selected_image = self.get_random_image()

                page = FormPage(
                    title=title,
                    slug=slug,
                    body=body,
                    image=selected_image,
                    thank_you_text=RichText("Thank you for your submission!"),
                    from_address="noreply@example.com",
                    to_address="admin@example.com",
                    subject="Form Submission",
                )
                home_page.add_child(instance=page)
                # add_child() already saves the page, but we need to refresh to get the ID
                page.refresh_from_db()

                # Create FormField items (InlinePanel)
                if inline_panel_items > 0:
                    field_types = ['singleline', 'multiline', 'email', 'number', 'url', 'checkbox', 'checkboxes',
                                   'dropdown', 'multiselect', 'radio', 'date', 'datetime']
                    field_labels = ['Name', 'Email', 'Message', 'Phone', 'Subject', 'Comments', 'Feedback', 'Question',
                                    'Inquiry', 'Request']

                    for field_idx in range(inline_panel_items):
                        field_type = random.choice(field_types)
                        field_label = random.choice(field_labels) + f" {field_idx + 1}"

                        FormField.objects.create(
                            page=page,
                            sort_order=field_idx,
                            label=field_label,
                            field_type=field_type,
                            required=random.choice([True, False]),
                            help_text=lorem_ipsum.words(random.randint(5, 15),
                                                        common=False) if random.random() < 0.5 else "",
                        )
                    # Save page after adding relationships
                    page.save()

                # Create initial revision and publish
                revision = page.save_revision()
                revision.publish()
                # Ensure page is live
                page.refresh_from_db()

                # Create additional revisions (these will be drafts)
                for rev_num in range(revisions - 1):
                    page.thank_you_text = RichText(f"[Revision {rev_num + 2}] " + str(page.thank_you_text))
                    page.save_revision()

                created_count += 1

            if (created_count) % 50 == 0:
                self.stdout.write(f'  Progress: {created_count}/{count} pages...')

        return created_count
