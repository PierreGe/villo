# -*- coding: utf-8 -*-

from flask import (
    Flask, render_template, g, redirect, url_for, escape, request, 
    make_response, flash
)
import os
from user import current_user, connect_user, disconnect_user
from datetime import datetime, timedelta
import config
from apputils import get_db

app = Flask(__name__)
app.secret_key = os.urandom(24)

def require_login(func):
    """
    Simple decorator that requires the user to be logged in to display the view,
    otherwise redirect to /login with a flahs message
    """
    def wrapper(*args, **kwargs):
        if not current_user():
            flash(u"Vous devez être connecté pour voir cette page", "warning")
            return redirect(url_for('login') + '?next=' + request.path)
        return func(*args, **kwargs)
    wrapper.__name__ = "login_required_" + func.__name__
    return wrapper


def require_admin(func):
    """
    Simple decorator that requires the user to be an admin to display the view,
    otherwise redirect to home with a flash message
    """
    def wrapper(*args, **kwargs):
        if not current_user() or not current_user().is_admin():
            flash(u"Cette page est réservée aux administrateurs seulement", "danger")
            return redirect("/")
        return func(*args, **kwargs)
    wrapper.__name__ = "admin_required_" + func.__name__
    return wrapper


@app.template_filter('plur')
def pluralize(number, singular='', plural='s'):
    """Template filter to pluralize a suffix according to a number"""
    if number == 1:
        return singular
    else:
        return plural


@app.template_filter('dt')
def format_timedelta(dt):
    """Format a time interval in french"""
    if isinstance(dt, timedelta):
        dt = dt.total_seconds()
    dt = int(dt)

    days, dt = dt//86400, dt%86400
    hours, dt = dt//3600, dt%3600
    minutes, seconds = dt//60, dt%60

    res = []
    if days: res.append(("%d jour" % days) + pluralize(days))
    if hours: res.append("%dh" % hours)
    if minutes: res.append("%dmin" % minutes)
    if seconds: res.append("%ds" % seconds)
    return ' '.join(res)


@app.context_processor
def user_processor():
    return {'user': current_user()}


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.route("/")
def index():
    user = current_user()
    if user:
        ctx = {}
        def month_displayname(date):
            months = ["Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin", "Juillet", "Aout", "Spetembre", "Octobre", "Novembre", "Decembre"]
            return "%s %d" % (months[date.month-1], date.year)

        trip_list = current_user().trips
        if trip_list:
            trips_by_month = []
            if len(trip_list) > 0:
                trips_by_month = [
                    (month_displayname(trip_list[0].departure_date), [trip_list[0]])
                ]
                for trip in trip_list[1:]:
                    name = month_displayname(trip.departure_date)
                    if name == trips_by_month[-1][0]:
                        trips_by_month[-1][1].append(trip)
                    else:
                        trips_by_month.append((name, [trip]))
            ctx["month_name"] = trips_by_month[0][0]
            ctx["month_trip_nbr"] = len(trips_by_month[0][1])
            price = 0
            kilometer = 0
            for t in trips_by_month[0][1]:
                price+= t.price()
                kilometer = t.distance()
            ctx["month_price"] = price
            ctx["month_kilometer"] = kilometer
        else:
            ctx["month_name"] = "Total"
            ctx["month_trip_nbr"] = 0
            ctx["month_price"] = 0
            ctx["month_kilometer"] = 0
        if user.is_admin():
            ctx['broken_bikes'] = get_db().Bike.allBroken()
        return render_template("dashboard.html", **ctx)
    return render_template("home.html")


@app.route('/session_status')
def session_status():
    if current_user():
        return 'Logged in as %s' % escape(current_user().id)
    return 'You are not logged in'

@app.route('/sqltest')
def sqltest():
    connect_user(get_db().User.get(0))
    return current_user().newUniqueRFID()

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_page = request.args['next'] if 'next' in request.args else url_for('index')
    if request.method == 'POST':
        try:
            user = get_db().User.get(int(request.form['userId']))
            if user.auth(request.form['userPassword']):
                connect_user(user)
                return redirect(next_page)
        except KeyError:
            pass
        return render_template("login.html", loginFailure=True)
    else:
        return render_template("login.html", next=next_page)


@app.route('/subscription', methods=['POST'])
def subscription():
    if current_user():
        current_user().renew()
        return redirect(url_for('index'))
    else:
        F = {k: v[0] for k,v in dict(request.form).iteritems()}
        print F
        if F['subscriber'] == 'true':
            new_user = get_db().User.create(
                password=F['userPassword'],
                card=F['userBankData'],
                firstname=F['userFirstName'],
                lastname=F['userLastName'],
                phone_number=F['userPhone'],
                address_street=F['userStreet'],
                address_streenumber= F['userNumber'] ,
                address_zipcode=F['userPostalCode'],
                address_city= F['userCity'],
                address_country=F['userCountry'],
                entry_date= datetime.now(),
                rfid= get_db().User.newUniqueRFID(),
                expire_date=datetime.now() + timedelta(days=365))
        else:
            dt = timedelta(days=7 if F['tempAmount'] == '7j' else 1)
            new_user = get_db().User.create(
                password=F['userPassword'],
                expire_date=datetime.now()+dt)
        connect_user(new_user)
        return render_template("welcome.html", user=new_user)


@app.route('/subscription', methods=['GET'])
def subscription_form():
    return render_template("subscription.html")


@app.route("/station")
def station():
    return render_template("station.html", station_list=get_db().Station.all())


@app.route("/map_station_popup/<int:station_id>")
def station_popup(station_id):
    ctx = {'station': get_db().Station.get(station_id)}
    return render_template("partials/map_station_popup.html", **ctx)


@app.route("/trip")
@require_login
def trip():
    return render_template("trip.html")

@app.route("/drop/<int:station_id>/bike/<int:bike_id>")
@require_login
def drop_bike(station_id, bike_id):
    user = current_user()
    if user.is_admin():
        active_trip = filter(lambda t: t.bike_id == bike_id, user.active_trips)
        if len(active_trip) != 1:
            flash(u"Vous n'utilisez actuellement pas le villo %d" % bike_id, "danger")
            return redirect("/")
        else:
            trip = active_trip.pop()
    else:
        trip = current_user().current_trip

    try:
        station = get_db().Station.get(station_id)
    except KeyError:
        flash(u"Station %d inconnue", "danger")
        return redirect("/")
    
    if not trip:
        flash(u"Vous n'avez pas de location en cours", "danger")
    elif trip.bike_id != bike_id:
        flash(u"Vous n'utilisez' actuellement pas le villo %d" % bike_id, "danger")
    elif station.free_slots == 0:
        flash(u"Il n'y a pas de point d'attache libre à %s" % station.name, "danger")
    else:
        trip.arrival_station_id = station_id
        trip.arrival_date = datetime.now()
        trip.update()
        flash(u"Vous avez déposé votre vélo à la station %s" % station.name, "success")
    return redirect("/")

@app.route("/station/<int:station_id>")
@require_login
def station_detail(station_id):
    try:
        station = get_db().Station.get(station_id)
    except KeyError:
        flash(u"Station %d inconnue", "warning")
        return redirect("/station")
    return render_template("rent.html", station=station)


@app.route("/rent/<int:station_id>/bike/<int:bike_id>")
@require_login
def rent_bike(station_id, bike_id):
    user = current_user()
    try:
        station = get_db().Station.get(station_id)
    except KeyError:
        flash(u"Station %d inconnue", "warning")
        return redirect("/station")
    
    if user.expired:
        flash(u"Renouvelez votre abonnement pour louer un villo", "danger")
        return redirect("/subscription")

    try:
        bike = get_db().Bike.get(bike_id)
    except KeyError:
        flash(u"Villo %d inconnu", "warning")
        return redirect("/rent/%d" % (station_id))

    if bike.location.id != station_id:
        flash(u"Le vélo %d ne se trouve pas à la station %s" % (bike_id, station.name), "danger")
    elif user.current_trip and not user.is_admin():
        flash(u"Vous avez déjà une location en cours", "danger")
    elif not bike.usable and not user.is_admin():
        flash(u"Ce villo n'est pas utilisable", "danger")
        return redirect("/rent/%d" % (station_id))
    else:
        get_db().Trip.create(
            user_id=user.id, bike_id=bike.id, 
            departure_station_id=station.id, departure_date=datetime.now())
        flash(u"Vous avez pris le villo %d à %s" % (bike.id, station.name), 'success')
    return redirect("/")


@app.route("/newbikes/<int:station_id>", methods=["POST"])
@require_admin
def newbikes(station_id):
    db = get_db()
    try:
        station = db.Station.get(station_id)
    except KeyError:
        flash(u"Station %d inconnue", "danger")
        return redirect("/")

    nBikes = int(request.form['bike_number'])
    model = request.form['bike_model'].strip()

    if nBikes > station.free_slots:
        flash(
            u"Pas assez de place à %s pour créer %d villos" % (station.name, nBikes), 
            "danger")
    elif model == "":
        flash(u"Le modèle de villo ne peut pas être vide", "danger")
    else:
        created = []
        for i in range(nBikes):
            bike = db.Bike.create(model=model)
            db.Trip.create(
                user_id=current_user().id, bike_id=bike.id,
                departure_station_id=station_id, departure_date=datetime.now(),
                arrival_station_id=station_id, arrival_date=datetime.now())
            created.append(str(bike.id))
        flash(pluralize(nBikes, u"Le vélo ", u"Les vélos ") +
              ', '.join(created) +
              pluralize(nBikes, u" a été ajouté", u" ont été ajoutés"), 
              "success")
    return redirect("/station/%d" % station_id)

@app.route("/history", methods=['POST'])
@require_login
def history_post():
    detail = "Date de debut;Date de fin;Station de depart;Station de fin\n"
    for trip in current_user().trips :
        detail+= str(trip.departure_date) + ";" + str(trip.arrival_date) + ";" + trip.arrival_station.name + ";" + trip.departure_station.name + "\n"
    response = make_response(detail)
    response.headers["Content-Disposition"] = "attachment; filename=trajet-details.csv"
    return response


@app.route("/history", methods=['GET'])
@require_login
def history():
    minkm = sum([float(x.distance()) for x in current_user().trips])
    def month_displayname(date):
        months = ["Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin", "Juillet", "Aout", "Spetembre", "Octobre", "Novembre", "Decembre"]
        return "%s %d" % (months[date.month-1], date.year)

    trip_list = current_user().trips
    trips_by_month = []
    if len(trip_list) > 0:
        trips_by_month = [
            (month_displayname(trip_list[0].departure_date), [trip_list[0]])
        ]
        for trip in trip_list[1:]:
            name = month_displayname(trip.departure_date)
            if name == trips_by_month[-1][0]:
                trips_by_month[-1][1].append(trip)
            else:
                trips_by_month.append((name, [trip]))
    return render_template("history.html",minimum_km=minkm, trips_by_month=trips_by_month)


@app.route("/problem/<int:bike_id>")
@require_login
def problem(bike_id):
    try:
        bike = get_db().Bike.get(bike_id)
        bike.updateUsable(False)
        flash(u"Le problème sur le vélo %d a été signalé" % bike.id, "success")
    except KeyError:
        flash(u"Le vélo %d n'existe pas" % bike_id, "danger")
    return redirect("/")


@app.route("/repair/<int:bike_id>")
@require_admin
def repair_bike(bike_id):
    try:
        bike = get_db().Bike.get(bike_id)
        if bike.usable:
            flash(u"Le vélo %d est déjà utilisable" % bike_id, "warning")
        else:
            bike.updateUsable(True)
            flash(u"Le vélo a été réparé", "success")
    except KeyError:
        flash(u"Vélo %d introuvable" % bike_id, "danger")
    return redirect("/")

@app.route("/billing", methods=['POST'])
@require_login
def billing_post():
    starting = current_user().expire_date - timedelta(days=(365))
    detail = "Type;Prix;Date de debut;Date de fin;Station de depart;Station de fin\n"
    detail += "Abonnement;32.6;"+starting.strftime("%d-%m-%Y")+";" +str(current_user().expire_date.strftime("%d-%m-%Y"))+ ";None;None\n"
    for trip in current_user().trips :
        if trip.departure_date > starting:
            detail+= "Trajet;" +str(trip.price()) + ";" +str(trip.departure_date) + ";" + str(trip.arrival_date) + ";" + trip.arrival_station.name + ";" + trip.departure_station.name + "\n"
            #detail += "De "+trip.departure_station.name+" ("+str(trip.departure_date)+") à "+trip.arrival_station.name+" ("+str(trip.arrival_date)+ ") : " + str(trip.price()) + "\n"
    response = make_response(detail)
    response.headers["Content-Disposition"] = "attachment; filename=facture-details.csv"
    return response

@app.route("/billing", methods=['GET'])
@require_login
def billing():
    if current_user().is_admin():
        return redirect("/")
    user = current_user()
    starting = user.expire_date - timedelta(days=(365))
    periodeFact = (starting.strftime("%d-%m-%Y"), str(user.expire_date.strftime("%d-%m-%Y")))
    billedTrip = user.billable_trips(to_time=user.expire_date)
    total = 32.60 + sum(map(lambda x: x.price(), billedTrip))
    return render_template("billing.html",periodeBilling = periodeFact, totalBilled=str(total), trip_list=billedTrip)


@app.route('/logout')
def logout():
    disconnect_user()
    return redirect(url_for('index'))


@app.route("/newstation", methods=["POST"])
@require_admin
def newstation():
    F = {k: v[0] for k,v in dict(request.form).iteritems()}
    print F
    latitude = float(F['latitude'])
    longitude = float(F['longitude'])
    capacity = int(F['capacity'])
    payment = 'payment' in F
    name = F['name'].upper()
    station = get_db().Station.create(
        capacity=capacity, name=name, payment=payment,
        latitude=latitude, longitude=longitude)
    return redirect("/station/%d" % station.id)

if __name__ == "__main__":
    app.run(
        debug=config.DEBUG, 
        host=config.WEB_ADDRESS, 
        port=config.WEB_PORT) # debug : server will reload itself on code changes
