from flask import abort
from flask import flash
from flask import Flask
from flask import render_template
from flask import request
from flask import url_for
from models import Listing
from models import ListingForm
import peewee
from wtfpeewee.orm import model_form

ListingForm = model_form(Listing, exclude=['title', 'url', 'source_time'])

app = Flask(__name__)

@app.template_filter('NoNone')
def NoNone(val):
  if val is not None:
    return val
  else:
    return ''

@app.route('/')
def Index():
  return render_template('index.html',
      listings=Listing.select().order_by(Listing.year))

@app.route('/listing/<int:listing_id>/', methods=['GET', 'POST'])
def ListingDetail(listing_id):
  try:
    listing = Listing.get(id=listing_id)
  except peewee.DoesNotExist:
    abort(404)

  if request.method == 'POST':
    form = ListingForm(request.form, obj=listing)
    if form.validate():
      form.populate_obj(listing)
      listing.save()
  else:
    form = ListingForm(obj=listing)

  return render_template('detail.html', form=form, listing=listing)

app.run()
