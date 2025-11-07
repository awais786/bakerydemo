import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management import call_command
from django.core.management.base import BaseCommand
from wagtail.models import Page, Site
from wagtail.images.models import Image


class Command(BaseCommand):
    def _copy_files(self, local_storage, path):
        """
        Recursively copy files from local_storage to default_storage. Used
        to automatically bootstrap the media directory (both locally and on
        cloud providers) with the images linked from the initial data (and
        included in MEDIA_ROOT).
        """
        directories, file_names = local_storage.listdir(path)
        for directory in directories:
            self._copy_files(local_storage, path + directory + "/")
        for file_name in file_names:
            with local_storage.open(path + file_name) as file_:
                default_storage.save(path + file_name, file_)

    def _load_people_data(self):
        """Load people/team data."""
        from bakerydemo.people.models import PeopleIndexPage, PersonPage

        # People data
        people_data = [
            {
                "first_name": "Tom",
                "last_name": "Dyson",
                "role": "Co-founder & Developer",
                "introduction": "One of the original creators of Wagtail CMS.",
                "location": "Bristol, UK",
                "team": "leadership",
                "github": "tomdyson",
                "bio": "<p>Tom is one of the co-founders of Wagtail and has been instrumental in its development.</p>",
            },
            {
                "first_name": "Matt",
                "last_name": "Westcott",
                "role": "Core Developer",
                "introduction": "Long-time Wagtail core team member and StreamField architect.",
                "location": "Oxford, UK",
                "team": "engineering",
                "github": "gasman",
                "bio": "<p>Matt is a long-time core contributor to Wagtail.</p>",
            },
            {
                "first_name": "Thibaud",
                "last_name": "Colas",
                "role": "Accessibility Lead",
                "introduction": "Focused on accessibility and front-end development.",
                "location": "Wellington, New Zealand",
                "team": "engineering",
                "github": "thibaudcolas",
                "twitter": "thibaud_colas",
                "bio": "<p>Thibaud works to ensure that Wagtail is usable by everyone.</p>",
            },
        ]

        image_mapping = {
            "tom-dyson": "lightnin_hopkins.jpg",
            "matt-westcott": "muddy_waters.jpg",
            "thibaud-colas": "sprint_crew.jpg",
        }

        # Find home page
        try:
            from bakerydemo.base.models import HomePage
            home_page = HomePage.objects.first()
            if not home_page:
                home_page = Page.objects.filter(depth=2).first()
        except ImportError:
            home_page = Page.objects.filter(depth=2).first()

        if not home_page:
            return

        # Create People Index if not exists
        people_index = PeopleIndexPage.objects.first()
        if not people_index:
            try:
                people_index = PeopleIndexPage(
                    title="Our Team",
                    slug="team",
                    introduction="Meet the amazing people who contribute to Wagtail CMS.",
                    show_in_menus=True,
                )
                home_page.add_child(instance=people_index)
                people_index.save_revision().publish()
                # Refresh from database to get the correct state
                people_index = PeopleIndexPage.objects.get(pk=people_index.pk)

                # Move Our Team after Gallery in menu order
                try:
                    # Find Gallery page
                    gallery_page = home_page.get_children().filter(title="Gallery").first()
                    if gallery_page:
                        # Move people_index to position after gallery
                        people_index.move(gallery_page, pos='right')
                        # Refresh again after move
                        people_index = PeopleIndexPage.objects.get(pk=people_index.pk)
                except Exception as e:
                    # Refresh from database even if move failed
                    people_index = PeopleIndexPage.objects.get(pk=people_index.pk)

            except Exception as e:
                return
        else:
            if not people_index.show_in_menus:
                people_index.show_in_menus = True
                people_index.save_revision().publish()
                # Refresh from database
                people_index = PeopleIndexPage.objects.get(pk=people_index.pk)

            # Ensure it's positioned after Gallery
            try:
                gallery_page = home_page.get_children().filter(title="Gallery").first()
                if gallery_page and people_index.get_parent() == gallery_page.get_parent():
                    # Check if people_index is not already after gallery
                    if people_index.path < gallery_page.path or not people_index.path.startswith(gallery_page.path[:len(gallery_page.path)-4]):
                        people_index.move(gallery_page, pos='right')
                        people_index = PeopleIndexPage.objects.get(pk=people_index.pk)
            except Exception:
                pass
        # Create person pages
        for person_data in people_data:
            slug = f"{person_data['first_name']}-{person_data['last_name']}".lower()
            full_name = f"{person_data['first_name']} {person_data['last_name']}"

            if PersonPage.objects.filter(slug=slug).exists():
                continue

            try:
                person_page = PersonPage(
                    title=full_name,
                    slug=slug,
                    first_name=person_data["first_name"],
                    last_name=person_data["last_name"],
                    role=person_data["role"],
                    introduction=person_data["introduction"],
                    location=person_data.get("location", ""),
                    team=person_data.get("team", ""),
                    github=person_data.get("github", ""),
                    twitter=person_data.get("twitter", ""),
                )

                if "bio" in person_data:
                    person_page.body = [("paragraph", person_data["bio"])]

                # Assign image
                image_name = image_mapping.get(slug)
                if image_name:
                    base_name = image_name.split(".")[0]
                    image = (
                        Image.objects.filter(file__icontains=base_name).first()
                        or Image.objects.filter(title__icontains=base_name).first()
                    )
                    if image:
                        person_page.profile_picture = image

                people_index.add_child(instance=person_page)
                person_page.save_revision().publish()
            except Exception:
                pass  # Skip person if creation fails, continue with others


    def handle(self, **options):
        fixtures_dir = os.path.join(settings.PROJECT_DIR, "base", "fixtures")
        fixture_file = os.path.join(fixtures_dir, "bakerydemo.json")

        print("Copying media files to configured storage...")  # noqa: T201
        local_storage = FileSystemStorage(os.path.join(fixtures_dir, "media"))
        self._copy_files(local_storage, "")  # file storage paths are relative

        # Wagtail creates default Site and Page instances during install, but we already have
        # them in the data load. Remove the auto-generated ones.
        if Site.objects.filter(hostname="localhost").exists():
            Site.objects.get(hostname="localhost").delete()
        if Page.objects.filter(title="Welcome to your new Wagtail site!").exists():
            Page.objects.get(title="Welcome to your new Wagtail site!").delete()

        call_command("loaddata", fixture_file, verbosity=0)
        call_command("update_index", verbosity=0)
        call_command("rebuild_references_index", verbosity=0)

        # Load people data
        print("Loading people data...")  # noqa: T201
        self._load_people_data()

        print(  # noqa: T201
            "Awesome. Your data is loaded! The bakery's doors are almost ready to open..."
        )
