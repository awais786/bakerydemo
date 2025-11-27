import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management import call_command
from django.core.management.base import BaseCommand
from wagtail.models import Page, Site
from wagtail.images.models import Image
from bakerydemo.base.models import HomePage
from bakerydemo.people.models import PeopleIndexPage, PersonPage


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

        # Get home page
        home_page = HomePage.objects.first()
        people_index = self._create_people_index(home_page)
        # Create person pages
        self._create_people_pages(people_data, image_mapping, people_index)

    def _create_people_index(self, home_page):
        """Create and position the People Index page."""
        try:
            people_index = PeopleIndexPage(
                title="Our Team",
                slug="team",
                introduction="Meet the amazing people who contribute to Wagtail CMS.",
                show_in_menus=True,
            )
            home_page.add_child(instance=people_index)
            people_index.save_revision().publish()
            people_index.refresh_from_db()

            # Move after Gallery
            gallery_page = home_page.get_children().filter(title="Gallery").first()
            if gallery_page:
                people_index.move(gallery_page, pos='right')
                people_index.refresh_from_db()

            return people_index
        except Exception:
            return None


    def _create_people_pages(self, people_data, image_mapping, people_index):
        """Create individual person pages."""
        for person_data in people_data:
            slug = f"{person_data['first_name']}-{person_data['last_name']}".lower()

            if PersonPage.objects.filter(slug=slug).exists():
                continue

            try:
                person_page = PersonPage(
                    title=f"{person_data['first_name']} {person_data['last_name']}",
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

                # Assign profile picture
                image = self._get_image(image_mapping.get(slug))
                if image:
                    person_page.profile_picture = image

                people_index.add_child(instance=person_page)
                person_page.save_revision().publish()
            except Exception:
                pass

    def _get_image(self, image_name):
        """Get image by filename."""
        base_name = image_name.split(".")[0]
        return Image.objects.filter(file__icontains=base_name).first()

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
        self._load_people_data()

        print(  # noqa: T201
            "Awesome. Your data is loaded! The bakery's doors are almost ready to open..."
        )
