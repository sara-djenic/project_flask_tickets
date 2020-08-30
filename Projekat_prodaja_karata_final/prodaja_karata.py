from flask import Flask, render_template, redirect, url_for, request, session
from pymongo import MongoClient
from flask_uploads import UploadSet, IMAGES, configure_uploads
from bson import ObjectId
import hashlib
import time

app = Flask(__name__)

photos = UploadSet('photos', IMAGES)
UPLOAD_FOLDER = 'static/img'
app.config['UPLOADED_PHOTOS_DEST'] = 'static'
configure_uploads(app, photos)
app.config['SECRET_KEY'] = 'NEKI RANDOM STRING'

client = MongoClient(
    "mongodb://admin:admin@cluster0-shard-00-00-pbeof.mongodb.net:27017,"
    "cluster0-shard-00-01-pbeof.mongodb.net:27017,cluster0-shard-00-02-pbeof"
    ".mongodb.net:27017/test?ssl=true&replicaSet=Cluster0-shard-0&authSource=admin&retryWrites=true&w=majority")

db = client.get_database("db_karte_rs")
col_users = db["col_korisnici"]
col_events = db["col_dogadjaji"]
col_purchases = db["col_kupovine"]


@app.route('/register', methods=["POST", "GET"])
def register():
    if request.method == 'GET':
        return render_template('register.html')

    if col_users.find_one({"username": request.form['username']}) is not None:
        return 'Korisnicko ime vec postoji!'

    username = request.form["username"]
    first_name = request.form["first_name"]
    surname = request.form["surname"]
    email = request.form["email"]
    password = request.form["password"]
    confirm_pass = request.form["confirm_pass"]
    if password != confirm_pass:
        return 'Lozinke se razlikuju. Unesite ponovo!'
    hash_object = hashlib.sha256(request.form['password'].encode())
    password_hashed = hash_object.hexdigest()
    user = {
        "_username": username,
        "_name": first_name,
        "_surname": surname,
        "_email": email,
        "_sifra": password_hashed,
        "_tipKorisnika": "kupac",
        "napravljeno": time.strftime("%d-%m-%Y.%H:%M:%S"),
    }

    col_users.insert_one(user)
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if '_id' in session and session["_id"] is not None:
        return "Vec ste ulogovani"
    if request.method == 'GET':
        return render_template('uloguj.html')
    else:
        hash_object = hashlib.sha256(request.form['password'].encode())
        password_hashed = hash_object.hexdigest()
        korisnik = col_users.find_one({'_username': request.form['username'], '_sifra': password_hashed})
        if korisnik is None:
            return 'Pogresno korisnicko ime ili lozinka!'
        session['_id'] = str(korisnik['_id'])
        session['type'] = korisnik['_tipKorisnika']
        return redirect(url_for('main'))


@app.route('/festivals', methods=['GET'])
def festivals():
    events_festivals = col_events.find({'_kategorijaDogadjaja': 'festivali'})
    user_type = None
    if 'type' in session:
        user_type = session['type']
    return render_template('festivali.html', events=events_festivals, user_type=user_type)


@app.route('/concerts', methods=['GET'])
def concerts():
    events_concerts = col_events.find({'_kategorijaDogadjaja': 'koncerti'})
    user_type = None
    if 'type' in session:
        user_type = session['type']
    return render_template('koncerti.html', events=events_concerts, user_type=user_type)


@app.route('/sport', methods=['GET'])
def sport():
    events_sport = col_events.find({'_kategorijaDogadjaja': 'sport'})
    user_type = None
    if 'type' in session:
        user_type = session['type']
    return render_template('sport.html', events=events_sport, user_type=user_type)


@app.route('/other', methods=['GET'])
def other():
    events = col_events.find()
    events_other = []
    for event in events:
        category = event['_kategorijaDogadjaja']
        if category != 'festivali' and category != 'koncerti' and category != 'sport':
            events_other.append(event)
    user_type = None
    if 'type' in session:
        user_type = session['type']
    return render_template('ostalo.html', events=events_other, user_type=user_type)


@app.route('/search/<search_text>', methods=['POST'])
def search(search_text):
    search_result = col_events.find({'$text': {'$search': search_text}})
    return render_template('other.html', search_result=search_result)  # todo prikazi rezultate na frontendu


@app.route('/buy_ticket/<event_id>', methods=['GET', 'POST'])
def buy_ticket(event_id):
    event = col_events.find_one({'_id': ObjectId(event_id)})
    if request.method == 'GET':
        return render_template('korpa.html', event=event)
    amount = int(request.form['amount'])
    current_ticket_number = event['_brKarataA']
    new_ticket_number = current_ticket_number - amount

    # ako je broj karata manji od 0 nije moguce zavrsiti kupovinu
    if new_ticket_number < 0:
        return f'Nije moguce kupiti zahtevani broj karata: {amount}. ' \
            f'Broj preostalih karata za ovaj dogadjaj je: {current_ticket_number}.'
    if amount < 1:
        return 'Molimo unesite pozitivan broj karata.'

    price = event['_cenaKarteA']
    total = float(amount) * price
    ticket = {
        '_idDogadjaj': event_id,
        '_idKorisnika': session['_id'],
        '_kolicina': amount,
        '_cenaKarte': price,
        '_ukupno': total,
        '_datumKupovine': time.strftime("%d-%m-%Y.%H:%M:%S"),
    }
    col_purchases.insert_one(ticket)

    # azuriraj broj karata za dogadjaj
    update_event = {"$set": {
        "_brKarataA": new_ticket_number,
    }}
    col_events.update_one(event, update_event)
    return redirect(url_for('main'))


@app.route('/add_event', methods=['GET', 'POST'])
def add_event():
    if 'type' in session and session['type'] != 'admin':
        return 'Samo administrator moze da unosi nove dogadjaje!'
    if request.method == 'GET':
        user_type = None
        if 'type' in session:
            user_type = session['type']
        return render_template('dodaj_dogadjaj.html', user_type=user_type)

    event_name = request.form['event_name']
    image_name = ''

    if 'event_image' in request.files:
        image_name = event_name + '.jpg'
        photos.save(request.files['event_image'], 'img', image_name)

    event = {
        '_kategorijaDogadjaja': request.form['category'],
        '_nazivDogadjaja': event_name,
        '_mestoDogadjaja': request.form['venue'],
        '_datumPocetkaDogadjaja': request.form['start_date'],
        '_vremePocetkaDogadjaja': request.form['start_time'],
        '_opisDogadjaja': request.form['description'],
        '_slikaDogadjaja': image_name,
        '_cenaKarteA': float(request.form['price']),
        '_brKarataA': int(request.form['number_of_tickets'])
    }
    col_events.insert_one(event)
    return redirect(url_for('main'))


@app.route('/logout')
def logout():
    if "_id" in session:
        session.pop('_id', None)
        session.pop('type', None)
        return redirect(url_for('main'))
    return redirect(url_for('main'))


@app.route('/')
@app.route('/main', methods=['GET'])
def main():
    user_type = None
    if 'type' in session:
        user_type = session['type']
    return render_template('main.html', user_type=user_type)


@app.route('/about', methods=['GET'])
def about():
    return render_template('onama.html')


@app.route('/categories', methods=['GET'])
def categories():
    return render_template('kategorije.html')


@app.route('/contact', methods=['GET'])
def contact():
    return render_template('kontakt.html')


@app.route('/help_page', methods=['GET'])
def help_page():
    return render_template('pomoc.html')


@app.route('/terms', methods=['GET'])
def terms():
    return render_template('uslovi.html')


@app.route('/privacy_policy', methods=['GET'])
def privacy_policy():
    return render_template('politika.html')


if __name__ == '__main__':
    app.run(debug=True)
