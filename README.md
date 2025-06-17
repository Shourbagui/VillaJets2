# VillaJets

Luxury Flight Management System

## Features

- Custom Django admin with Unfold theme
- Document management and extraction
- Flight and client management
- Mail integration

## Requirements

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)

## Setup

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd villaajets
   ```

2. **Install dependencies:**
   ```bash
   poetry install
   ```

3. **Activate the virtual environment:**
   ```bash
   poetry shell
   ```

4. **Apply migrations:**
   ```bash
   python manage.py migrate
   ```

5. **Run the development server:**
   ```bash
   python manage.py runserver
   ```

## Usage

- Access the admin at [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)
- Default admin user: *(add instructions for creating a superuser if needed)*

## Testing

```bash
python manage.py test
```

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](LICENSE)
