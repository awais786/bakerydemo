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
from bakerydemo.base.models import FormField, FormPage, HomePage, Person, StandardPage
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
BLOG_PAGES = 50
BREAD_PAGES = 50
LOCATION_PAGES = 0
FORM_PAGES = 0
STANDARD_PAGES = 0


class Command(BaseCommand):
    help = 'Load benchmark data for performance testing using existing content types'

    def handle(self, *args, **options):
        blog_count = BLOG_PAGES
        bread_count = BREAD_PAGES
        location_count = LOCATION_PAGES
        form_count = FORM_PAGES
        standard_count = STANDARD_PAGES

        self.stdout.write(self.style.SUCCESS('Starting benchmark data generation...'))
        self.stdout.write(
            f'Target: {blog_count} blog, {bread_count} bread, {location_count} location, '
            f'{form_count} form, {standard_count} standard pages'
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
            self.stdout.write('\nCreating blog pages...')
            created = self.create_blog_pages(home_page, blog_count)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created} new blog pages'))

        # Create bread pages
        if bread_count > 0:
            self.stdout.write('\nCreating bread pages...')
            created = self.create_bread_pages(home_page, bread_count)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created} new bread pages'))

        # Create location pages
        if location_count > 0:
            self.stdout.write('\nCreating location pages...')
            created = self.create_location_pages(home_page, location_count)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created} new location pages'))

        # Create form pages
        if form_count > 0:
            self.stdout.write('\nCreating form pages...')
            created = self.create_form_pages(home_page, form_count)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created} new form pages'))

        # Create standard pages
        if standard_count > 0:
            self.stdout.write('\nCreating standard pages...')
            created = self.create_standard_pages(home_page, standard_count)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created} new standard pages'))

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

    def _create_block_quote(self, position, nest_interval, max_nesting):
        """Create a block quote, nested if appropriate."""
        if nest_interval and position % nest_interval == 0:
            nesting_level = min(position // nest_interval, max_nesting)
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
        """
        blocks = []
        paragraph_count = 0

        # Calculate nesting interval if nesting is enabled
        # Ensure nest_interval is never 0 to avoid ZeroDivisionError
        nest_interval = None
        if max_nesting > 0 and num_blocks > 0:
            # Use max(1, ...) to ensure we never divide by 0
            # When num_blocks < max_nesting, we'll get a smaller interval
            nest_interval = max(1, num_blocks // max(1, max_nesting))

        for i in range(num_blocks):
            # Prioritize paragraphs if we need more
            if num_paragraphs > 0 and paragraph_count < num_paragraphs:
                blocks.append(self._create_paragraph_block(min_paragraphs=2, max_paragraphs=5))
                paragraph_count += 1
                continue

            # Cycle through 4 block types: 0=heading, 1=block_quote, 2=heading, 3=paragraph
            block_type = i % 4

            if block_type == 1:  # block_quote
                blocks.append(self._create_block_quote(i, nest_interval, max_nesting))
            elif block_type == 3:  # paragraph
                blocks.append(self._create_paragraph_block())
                paragraph_count += 1
            else:  # block_type in (0, 2) - heading blocks
                blocks.append(self._create_heading_block())

        return blocks

    def _publish_page_with_revisions(self, page, revisions):
        """Common helper to publish a page and create additional revisions."""
        revision = page.save_revision()
        revision.publish()
        page.refresh_from_db()

        # Create additional revisions (these will be drafts)
        for rev_num in range(revisions - 1):
            page.introduction = f"[Revision {rev_num + 2}] " + page.introduction
            page.save_revision()

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
            for i in range(max(10, inline_panel_items)):
                people.append(Person.objects.create(
                    first_name=lorem_ipsum.words(1, common=False),
                    last_name=lorem_ipsum.words(1, common=False),
                    job_title=lorem_ipsum.words(2, common=False),
                ))

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

                # Create initial revision and publish, then create additional revisions
                self._publish_page_with_revisions(page, revisions)

                created_count += 1

            if (created_count) % 50 == 0:
                self.stdout.write(f'  Progress: {created_count}/{count} pages...')

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

        for i in range(count):
            page_number = start_number + i
            bread_type_name = random.choice(bread_type_names)
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

                # Create initial revision and publish, then create additional revisions
                self._publish_page_with_revisions(page, revisions)

                created_count += 1

            if (created_count) % 50 == 0:
                self.stdout.write(f'  Progress: {created_count}/{count} pages...')

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

    def _create_operating_hours(self, page, inline_panel_items):
        """Create LocationOperatingHours items for a location page."""
        days = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
        time_slots = [
            (time(6, 0), time(12, 0)),  # Morning
            (time(12, 0), time(18, 0)),  # Afternoon
            (time(18, 0), time(22, 0)),  # Evening
        ]

        for hour_idx in range(inline_panel_items):
            day = days[hour_idx % len(days)]
            time_slot = time_slots[hour_idx % len(time_slots)]
            LocationOperatingHours.objects.create(
                location=page,
                day=day,
                opening_time=time_slot[0],
                closing_time=time_slot[1],
                closed=(day in ['SAT', 'SUN'] and random.random() < 0.3)
            )
        page.save()

    def create_location_pages(self, home_page, count):
        """Create location pages using existing LocationPage model"""
        revisions = REVISIONS_PER_PAGE
        streamfield_blocks = STREAMFIELD_BLOCKS
        inline_panel_items = INLINE_PANEL_ITEMS
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

        for i in range(count):
            city = random.choice(cities)
            page_number = start_number + i
            title = f"{city} Location #{page_number}"
            slug = slugify(title)

            if LocationPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                body = self.generate_streamfield(streamfield_blocks, max_nesting=streamfield_nesting)
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

                if inline_panel_items > 0:
                    self._create_operating_hours(page, inline_panel_items)

                # Create initial revision and publish, then create additional revisions
                self._publish_page_with_revisions(page, revisions)

                created_count += 1

            if (created_count) % 50 == 0:
                self.stdout.write(f'  Progress: {created_count}/{count} pages...')

        return created_count

    def create_form_pages(self, home_page, count):
        """Create form pages using existing FormPage model"""
        revisions = REVISIONS_PER_PAGE
        streamfield_blocks = STREAMFIELD_BLOCKS
        inline_panel_items = INLINE_PANEL_ITEMS
        streamfield_nesting = STREAMFIELD_NESTING

        # Find the highest existing form page number
        def extract_form_number(title):
            return int(title.split()[-1])

        start_number = self._find_max_page_number(FormPage, 'Form Page', extract_form_number) + 1
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
                page.refresh_from_db()

                # Create additional revisions (these will be drafts)
                # Note: FormPage uses thank_you_text instead of introduction
                for rev_num in range(revisions - 1):
                    page.thank_you_text = RichText(f"[Revision {rev_num + 2}] " + str(page.thank_you_text))
                    page.save_revision()

                created_count += 1

            if (created_count) % 50 == 0:
                self.stdout.write(f'  Progress: {created_count}/{count} pages...')

        return created_count

    def create_standard_pages(self, home_page, count):
        """Create standard pages using existing StandardPage model"""
        revisions = REVISIONS_PER_PAGE
        streamfield_blocks = STREAMFIELD_BLOCKS
        streamfield_nesting = STREAMFIELD_NESTING

        # Find the highest existing standard page number
        def extract_standard_number(title):
            return int(title.split()[-1]) if title.split()[-1].isdigit() else None

        start_number = self._find_max_page_number(StandardPage, 'Standard Page', extract_standard_number) + 1
        created_count = 0

        for i in range(count):
            page_number = start_number + i
            title = f"Standard Page {page_number}"
            slug = slugify(title)

            if StandardPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                # Generate StreamField body
                body = self.generate_streamfield(streamfield_blocks, max_nesting=streamfield_nesting)

                # Get random image
                selected_image = self.get_random_image()

                page = StandardPage(
                    title=title,
                    slug=slug,
                    introduction=lorem_ipsum.paragraph(),
                    body=body,
                    image=selected_image,
                )
                home_page.add_child(instance=page)
                page.refresh_from_db()

                # Create initial revision and publish, then create additional revisions
                self._publish_page_with_revisions(page, revisions)

                created_count += 1

        return created_count
