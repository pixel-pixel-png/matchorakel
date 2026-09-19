"""Ett kommando för nya ligamatcher, omträning och valfritt spelschema."""
import os

from fetch_data import main as fetch_matches
from train_model import main as train_models
from update_fixtures import main as fetch_fixtures


def main():
    print('1/3: Hämtar färdiga ligamatcher...')
    fetch_matches()
    print('2/3: Tränar och utvärderar modellerna på nytt...')
    train_models()
    if os.environ.get('FOOTBALL_DATA_TOKEN'):
        print('3/3: Hämtar aktuellt spelschema...')
        fetch_fixtures()
    else:
        print('3/3: Spelschemat uppdaterades inte (ingen FOOTBALL_DATA_TOKEN i miljön).')
        print('Kör py update_fixtures.py om du vill ange nyckeln manuellt.')
    print('Klart. Starta om py app.py för att använda de nya modellerna.')


if __name__ == '__main__':
    main()
