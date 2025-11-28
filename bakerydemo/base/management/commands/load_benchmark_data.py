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
        self.stdout.write('Starting benchmark data generation.')
    
        try:
            home_page = Site.objects.get(is_default_site=True).root_page
        except (Site.DoesNotExist, Site.MultipleObjectsReturned) as e:
            self.stdout.write(self.style.ERROR(f'Could not find home page: {e}. Please set up the site first.'))
            return

        if BLOG_PAGES > 0:
            self.stdout.write('Creating blog pages...')
            created = self.create_blog_pages(home_page, BLOG_PAGES)
            self.stdout.write(f'Created {created} new blog pages')

        if BREAD_PAGES > 0:
            self.stdout.write('Creating bread pages...')
            created = self.create_bread_pages(home_page, BREAD_PAGES)
            self.stdout.write(f'Created {created} new bread pages')

        if LOCATION_PAGES > 0:
            self.stdout.write('Creating location pages...')
            created = self.create_location_pages(home_page, LOCATION_PAGES)
            self.stdout.write(f'Created {created} new location pages')

        self.stdout.write('Benchmark data generation complete!')

    def _get_images_cache(self):
        """Cache images to avoid repeated queries."""
        if not hasattr(self, '_images_cache'):
            self._images_cache = list(Image.objects.all())
        return self._images_cache

    def get_random_image(self):
        """Return a random image or None if no images exist."""
        images = self._get_images_cache()
        return random.choice(images) if images else None

    def _generate_paragraph(self):
        """Generate a random lorem ipsum paragraph."""
        return lorem_ipsum.paragraph()

    def generate_nested_block_quote(self, depth, max_depth):
        """Generate nested block quote with level prefixes."""
        settings = {
            'theme': random.choice(['default', 'highlight']),
            'text_size': random.choice(['default', 'large'])
        }
        
        if depth >= max_depth:
            return {
                'text': self._generate_paragraph(),
                'attribute_name': lorem_ipsum.words(2, common=False),
                'settings': settings
            }

        level_prefixes = [f"[Level {level}]" for level in range(1, depth + 1)]
        nested_text = " ".join(level_prefixes) + " " + self._generate_paragraph()

        return {
            'text': nested_text,
            'attribute_name': lorem_ipsum.words(2, common=False),
            'settings': settings
        }

    def _create_heading_block(self):
        """Create a heading block with random text."""
        return ('heading_block', {
            'heading_text': lorem_ipsum.words(random.randint(3, 8), common=False),
            'size': random.choice(['h2', 'h3', 'h4', ''])
        })

    def _create_paragraph_block(self, min_paragraphs=1, max_paragraphs=3):
        """Create a paragraph block with random paragraphs."""
        paragraph_text = '\n'.join(lorem_ipsum.paragraphs(random.randint(min_paragraphs, max_paragraphs)))
        return ('paragraph_block', RichText(paragraph_text))

    def _create_block_quote(self, block_quote_index, nest_interval, max_nesting):
        """Create a block quote, optionally nested based on index."""
        if nest_interval and block_quote_index > 0 and block_quote_index % nest_interval == 0:
            nesting_level = min(block_quote_index // nest_interval, max_nesting)
            return ('block_quote', self.generate_nested_block_quote(nesting_level, max_nesting))
        
        return ('block_quote', {
            'text': self._generate_paragraph(),
            'attribute_name': lorem_ipsum.words(2, common=False),
            'settings': {
                'theme': random.choice(['default', 'highlight']),
                'text_size': random.choice(['default', 'large'])
            }
        })

    def generate_streamfield(self, num_blocks, num_paragraphs=0, max_nesting=0):
        """Generate StreamField blocks cycling through heading, block_quote, paragraph."""
        blocks = []
        block_quote_count = 0
        
        nest_interval = None
        if max_nesting > 0:
            nest_interval = max(1, num_blocks // max(1, max_nesting * 10))

        for i in range(num_blocks):
            block_type = i % 4
            
            if block_type == 0 or block_type == 2:
                blocks.append(self._create_heading_block())
            elif block_type == 1:
                blocks.append(self._create_block_quote(block_quote_count, nest_interval, max_nesting))
                block_quote_count += 1
            else:
                if num_paragraphs > 0:
                    blocks.append(self._create_paragraph_block(min_paragraphs=2, max_paragraphs=5))
                else:
                    blocks.append(self._create_paragraph_block())

        return blocks

    def _publish_page_with_revisions(self, page, revisions):
        """Publish page and create additional draft revisions."""
        original_introduction = page.introduction
        
        revision = page.save_revision()
        revision.publish()
        page.refresh_from_db()

        for rev_num in range(revisions - 1):
            page.introduction = f"[Revision {rev_num + 2}] " + original_introduction
            page.save_revision()
        
        page.introduction = original_introduction
        page.refresh_from_db()

    def _find_max_page_number(self, model, title_prefix, extract_number_func):
        """Find the highest page number for a given model and title prefix."""
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
        """Create blog pages with relationships, tags, and streamfield content."""
        blog_index = BlogIndexPage.objects.filter(slug='blog').first()
        if not blog_index:
            self.stdout.write(self.style.WARNING('  Blog index not found. Skipping blog pages.'))
            return 0

        people = list(Person.objects.all())
        if not people and INLINE_PANEL_ITEMS > 0:
            self.stdout.write(self.style.WARNING('  No Person objects found. Creating sample people...'))
            people_to_create = [
                Person(
                    first_name=lorem_ipsum.words(1, common=False),
                    last_name=lorem_ipsum.words(1, common=False),
                    job_title=lorem_ipsum.words(2, common=False),
                )
                for _ in range(max(10, INLINE_PANEL_ITEMS))
            ]
            Person.objects.bulk_create(people_to_create)
            people = list(Person.objects.all())

        start_number = self._find_max_page_number(BlogPage, 'Blog Post', lambda title: int(title.split()[-1])) + 1

        tag_names = ['baking', 'bread', 'recipe', 'cooking', 'food', 'bakery', 'yeast', 'dough', 'pastry', 'dessert']
        tags = [Tag.objects.get_or_create(name=name)[0] for name in tag_names]

        body = self.generate_streamfield(STREAMFIELD_BLOCKS, RICH_TEXT_PARAGRAPHS, max_nesting=STREAMFIELD_NESTING)

        created_count = 0
        for i in range(count):
            page_number = start_number + i
            title = f"Blog Post {page_number}"
            slug = slugify(title)

            if BlogPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                page = BlogPage(
                    title=title,
                    slug=slug,
                    subtitle=lorem_ipsum.words(random.randint(5, 12), common=False),
                    introduction=self._generate_paragraph(),
                    body=body,
                    image=self.get_random_image(),
                    date_published=date.today(),
                )
                blog_index.add_child(instance=page)
                page.refresh_from_db()

                if INLINE_PANEL_ITEMS > 0 and people:
                    selected_people = random.sample(people, min(INLINE_PANEL_ITEMS, len(people)))
                    BlogPersonRelationship.objects.bulk_create([
                        BlogPersonRelationship(page=page, person=person)
                        for person in selected_people
                    ])

                if tags:
                    page.tags.add(*random.sample(tags, min(random.randint(2, 5), len(tags))))

                self._publish_page_with_revisions(page, REVISIONS_PER_PAGE)
                created_count += 1

        return created_count

    def create_bread_pages(self, home_page, count):
        """Create bread pages with random types, origins, and ingredients."""
        breads_index = BreadsIndexPage.objects.filter(slug='breads').first()
        if not breads_index:
            self.stdout.write(self.style.WARNING('  Breads index not found. Skipping bread pages.'))
            return 0

        bread_type_names = ['Sourdough', 'Baguette', 'Ciabatta', 'Rye', 'Whole Wheat',
                            'Multigrain', 'Pumpernickel', 'Focaccia', 'Challah', 'Brioche',
                            'Naan', 'Pita', 'Cornbread', 'Flatbread', 'Tortilla']
        country_names = ['France', 'Italy', 'Germany', 'United States', 'United Kingdom',
                         'Spain', 'Greece', 'Turkey', 'India', 'Mexico', 'Canada', 'Australia']
        ingredient_names = ['Flour', 'Water', 'Yeast', 'Salt', 'Sugar', 'Olive Oil',
                            'Butter', 'Eggs', 'Milk', 'Honey', 'Seeds', 'Nuts']

        bread_types = [BreadType.objects.get_or_create(title=name)[0] for name in bread_type_names]
        countries = [Country.objects.get_or_create(title=name)[0] for name in country_names]
        ingredients = [BreadIngredient.objects.get_or_create(name=name)[0] for name in ingredient_names]

        def extract_bread_number(title):
            if '#' in title:
                parts = title.split('#')
                if len(parts) > 1:
                    return int(parts[-1].strip())
            return None

        start_number = self._find_max_page_number(BreadPage, '', extract_bread_number) + 1
        body = self.generate_streamfield(STREAMFIELD_BLOCKS, max_nesting=STREAMFIELD_NESTING)

        created_count = 0
        for i in range(count):
            page_number = start_number + i
            title = f"{random.choice(bread_type_names)} #{page_number}"
            slug = slugify(title)

            if BreadPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                page = BreadPage(
                    title=title,
                    slug=slug,
                    introduction=self._generate_paragraph(),
                    body=body,
                    bread_type=random.choice(bread_types),
                    origin=random.choice(countries) if countries else None,
                    image=self.get_random_image(),
                )
                breads_index.add_child(instance=page)
                page.refresh_from_db()

                if ingredients:
                    page.ingredients.set(random.sample(ingredients, min(random.randint(3, 8), len(ingredients))))

                self._publish_page_with_revisions(page, REVISIONS_PER_PAGE)
                created_count += 1

        return created_count

    def _find_max_location_page_number(self):
        """Find the highest location page number."""
        def extract_location_number(title):
            if '#' in title:
                parts = title.split('#')
                if len(parts) > 1:
                    return int(parts[-1].strip())
            return None
        return self._find_max_page_number(LocationPage, '', extract_location_number)

    def _generate_location_address(self, city):
        """Generate a random address for the given city."""
        street_number = random.randint(1, 999)
        street_name = random.choice(['Main Street', 'Oak Avenue', 'Park Road', 'High Street', 'Church Lane'])
        country = random.choice(['Iceland', 'United States', 'United Kingdom', 'France', 'Germany'])
        return f"{street_number} {street_name},\r\n{city},\r\n{country}"

    def _generate_lat_long(self):
        """Generate random latitude and longitude coordinates."""
        lat = random.uniform(-90, 90)
        lng = random.uniform(-180, 180)
        return f"{lat:.6f}, {lng:.6f}"

    def _create_operating_hours(self, page):
        """Create operating hours for all days of the week."""
        operating_hours = [
            LocationOperatingHours(location=page, day='MON', opening_time=time(9, 0), closing_time=time(17, 0), closed=False),
            LocationOperatingHours(location=page, day='TUE', opening_time=time(9, 0), closing_time=time(17, 0), closed=False),
            LocationOperatingHours(location=page, day='WED', opening_time=time(9, 0), closing_time=time(17, 0), closed=False),
            LocationOperatingHours(location=page, day='THU', opening_time=time(9, 0), closing_time=time(17, 0), closed=False),
            LocationOperatingHours(location=page, day='FRI', opening_time=time(9, 0), closing_time=time(17, 0), closed=False),
            LocationOperatingHours(location=page, day='SAT', opening_time=time(10, 0), closing_time=time(16, 0), closed=False),
            LocationOperatingHours(location=page, day='SUN', opening_time=time(10, 0), closing_time=time(16, 0), closed=False),
        ]
        LocationOperatingHours.objects.bulk_create(operating_hours)

    def create_location_pages(self, home_page, count):
        """Create location pages with addresses, coordinates, and operating hours."""
        locations_index = LocationsIndexPage.objects.filter(slug='locations').first()
        if not locations_index:
            self.stdout.write(self.style.WARNING('  Locations index not found. Skipping location pages.'))
            return 0

        cities = ['New York', 'London', 'Paris', 'Tokyo', 'Sydney', 'Berlin',
                  'Toronto', 'Mumbai', 'Singapore', 'Dubai', 'Barcelona', 'Amsterdam',
                  'Rome', 'Madrid', 'Seoul', 'San Francisco', 'Chicago', 'Boston']

        start_number = self._find_max_location_page_number() + 1
        body = self.generate_streamfield(STREAMFIELD_BLOCKS, max_nesting=STREAMFIELD_NESTING)

        created_count = 0
        for i in range(count):
            city = random.choice(cities)
            title = f"{city} Location #{start_number + i}"
            slug = slugify(title)

            if LocationPage.objects.filter(slug=slug).exists():
                continue

            with transaction.atomic():
                page = LocationPage(
                    title=title,
                    slug=slug,
                    introduction=self._generate_paragraph(),
                    body=body,
                    address=self._generate_location_address(city),
                    lat_long=self._generate_lat_long(),
                    image=self.get_random_image(),
                )
                locations_index.add_child(instance=page)
                page.refresh_from_db()

                self._create_operating_hours(page)
                self._publish_page_with_revisions(page, REVISIONS_PER_PAGE)
                created_count += 1

        return created_count
