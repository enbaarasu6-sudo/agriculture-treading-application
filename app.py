from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3, os
from datetime import datetime

BASE=os.path.dirname(os.path.abspath(__file__)); DB=os.path.join(BASE,'agridirect.db')
app=Flask(__name__); app.config['SECRET_KEY']='agridirect-local-secret-change-me'

def db():
    if 'db' not in g:
        g.db=sqlite3.connect(DB); g.db.row_factory=sqlite3.Row
    return g.db
@app.teardown_appcontext
def close(e=None):
    x=g.pop('db',None)
    if x: x.close()
def init_db():
    d=db(); d.executescript('''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,location TEXT DEFAULT 'Local area');
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,farmer_id INTEGER NOT NULL,name TEXT NOT NULL,category TEXT NOT NULL,quantity INTEGER NOT NULL,unit TEXT NOT NULL,price REAL NOT NULL,harvested TEXT NOT NULL DEFAULT 'Today',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,consumer_id INTEGER NOT NULL,total REAL NOT NULL,address TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Placed',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL,product_id INTEGER NOT NULL,farmer_id INTEGER NOT NULL,quantity INTEGER NOT NULL,price REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,message TEXT NOT NULL,read INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS future_harvests(id INTEGER PRIMARY KEY AUTOINCREMENT,farmer_id INTEGER NOT NULL,crop TEXT NOT NULL,category TEXT NOT NULL,quantity INTEGER NOT NULL,unit TEXT NOT NULL,harvest_date TEXT NOT NULL,expected_price REAL NOT NULL,status TEXT NOT NULL DEFAULT 'Open',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wishlist(id INTEGER PRIMARY KEY AUTOINCREMENT,consumer_id INTEGER NOT NULL,product_id INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(consumer_id,product_id));
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,consumer_id INTEGER NOT NULL,product_id INTEGER NOT NULL,rating INTEGER NOT NULL,comment TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(consumer_id,product_id));
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL,consumer_id INTEGER NOT NULL,amount REAL NOT NULL,payment_method TEXT NOT NULL,transaction_id TEXT, status TEXT NOT NULL DEFAULT 'Pending',paid_at TEXT,created_at TEXT NOT NULL);
'''); d.commit()
with app.app_context(): init_db()

def user():
    uid=session.get('uid'); return db().execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone() if uid else None

def require(role):
 def deco(f):
  @wraps(f)
  def w(*a,**k):
   u=user()
   if not u: return redirect(url_for('login',role=role))
   if u['role']!=role: return redirect(url_for('farmer_home' if u['role']=='farmer' else 'consumer_home'))
   return f(*a,**k)
  return w
 return deco

def rows(sql,args=()): return db().execute(sql,args).fetchall()
def cart_products():
 cart=session.get('cart',{}); out=[]
 for pid,q in cart.items():
  p=db().execute('''SELECT p.*,u.name farmer FROM products p JOIN users u ON p.farmer_id=u.id WHERE p.id=?''',(pid,)).fetchone()
  if p: out.append((p,int(q)))
 return out

def wishlist_ids(consumer_id):
    return {r['product_id'] for r in db().execute('SELECT product_id FROM wishlist WHERE consumer_id=?',(consumer_id,)).fetchall()}

def price_advice(product):
    d=db()
    # Use AgriDirect's own order history as the pricing signal.
    hist=d.execute('''
        SELECT COALESCE(SUM(oi.quantity),0) qty,
               COALESCE(SUM(oi.quantity * oi.price),0) value
        FROM order_items oi
        JOIN orders o ON o.id=oi.order_id
        JOIN products p ON p.id=oi.product_id
        WHERE oi.farmer_id=? AND (p.id=? OR p.category=?)
    ''',(product['farmer_id'],product['id'],product['category'])).fetchone()
    avg=(hist['value']/hist['qty']) if hist['qty'] else float(product['price'])

    recent=d.execute('''
        SELECT COALESCE(SUM(oi.quantity),0) qty FROM order_items oi
        JOIN orders o ON o.id=oi.order_id
        JOIN products p ON p.id=oi.product_id
        WHERE oi.farmer_id=? AND (p.id=? OR p.category=?)
          AND datetime(o.created_at) >= datetime('now','-30 day')
    ''',(product['farmer_id'],product['id'],product['category'])).fetchone()['qty']
    previous=d.execute('''
        SELECT COALESCE(SUM(oi.quantity),0) qty FROM order_items oi
        JOIN orders o ON o.id=oi.order_id
        JOIN products p ON p.id=oi.product_id
        WHERE oi.farmer_id=? AND (p.id=? OR p.category=?)
          AND datetime(o.created_at) >= datetime('now','-60 day')
          AND datetime(o.created_at) < datetime('now','-30 day')
    ''',(product['farmer_id'],product['id'],product['category'])).fetchone()['qty']

    if previous == 0 and recent > 0:
        demand_factor=1.08; trend='Rising'
    elif previous == 0:
        demand_factor=1.0; trend='Not enough recent sales'
    else:
        change=(recent-previous)/previous
        if change >= 0.15:
            demand_factor=1.08; trend='Rising'
        elif change <= -0.15:
            demand_factor=0.94; trend='Softening'
        else:
            demand_factor=1.0; trend='Stable'

    if product['quantity'] <= 5:
        supply_factor=1.04; supply='Low stock'
    elif product['quantity'] >= 30:
        supply_factor=0.95; supply='High stock'
    else:
        supply_factor=1.0; supply='Balanced stock'

    suggested=max(1, round(avg*demand_factor*supply_factor,2))
    low=round(suggested*0.95,2); high=round(suggested*1.05,2)
    if hist['qty']:
        reason=f"Based on an AgriDirect historical average of ₹{avg:.2f}, {trend.lower()} demand and {supply.lower()}."
        source='AgriDirect sales history'
    else:
        low=round(float(product['price'])*0.95,2); high=round(float(product['price'])*1.05,2)
        suggested=round(float(product['price']),2)
        reason='No matching sales history yet, so the current listing price is used as the starting point.'
        source='Current listing price'
    return {'suggested':suggested,'low':low,'high':high,'trend':trend,'supply':supply,'reason':reason,'source':source}
def future_harvest_advice(farmer_id, crop, category):
    d=db()
    recent=d.execute("""SELECT COALESCE(SUM(oi.quantity),0) qty FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id WHERE p.category=? AND lower(p.name)=lower(?) AND datetime(o.created_at)>=datetime('now','-30 day')""",(category,crop)).fetchone()['qty']
    previous=d.execute("""SELECT COALESCE(SUM(oi.quantity),0) qty FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id WHERE p.category=? AND lower(p.name)=lower(?) AND datetime(o.created_at)>=datetime('now','-60 day') AND datetime(o.created_at)<datetime('now','-30 day')""",(category,crop)).fetchone()['qty']
    if previous == 0 and recent > 0: trend='Rising'
    elif previous == 0: trend='Not enough sales'
    else:
        change=(recent-previous)/previous
        trend='Rising' if change >= .15 else ('Softening' if change <= -.15 else 'Stable')
    sample=d.execute('SELECT * FROM products WHERE farmer_id=? AND lower(name)=lower(?) ORDER BY id DESC LIMIT 1',(farmer_id,crop)).fetchone()
    if sample:
        a=price_advice(sample); low,high=a['low'],a['high']
    else:
        hist=d.execute("""SELECT COALESCE(SUM(oi.quantity),0) qty,COALESCE(SUM(oi.quantity*oi.price),0) value FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id WHERE p.category=? AND lower(p.name)=lower(?)""",(category,crop)).fetchone()
        base=(hist['value']/hist['qty']) if hist['qty'] else 0
        if not base:
            cat_hist=d.execute("""SELECT COALESCE(SUM(oi.quantity),0) qty,COALESCE(SUM(oi.quantity*oi.price),0) value FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id WHERE p.category=?""",(category,)).fetchone()
            base=(cat_hist['value']/cat_hist['qty']) if cat_hist['qty'] else 0
        factor=1.08 if trend=='Rising' else (.94 if trend=='Softening' else 1.0)
        low=round(base*factor*.95,2) if base else 0; high=round(base*factor*1.05,2) if base else 0
    if trend=='Rising': status='Good to grow'
    elif trend=='Softening': status='Grow carefully'
    else: status='Plan normally'
    return {'trend':trend,'low':low,'high':high,'status':status}

def future_harvest_intelligence(farmer_id, crop, category, planned_qty, unit):
    """Compare a farmer's planned future harvest with AgriDirect demand."""
    d=db()
    recent=d.execute("""SELECT COALESCE(SUM(oi.quantity),0) qty
        FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id
        WHERE p.category=? AND lower(p.name)=lower(?)
          AND datetime(o.created_at)>=datetime('now','-30 day')""",(category,crop)).fetchone()['qty']
    previous=d.execute("""SELECT COALESCE(SUM(oi.quantity),0) qty
        FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id
        WHERE p.category=? AND lower(p.name)=lower(?)
          AND datetime(o.created_at)>=datetime('now','-60 day')
          AND datetime(o.created_at)<datetime('now','-30 day')""",(category,crop)).fetchone()['qty']

    if previous == 0 and recent > 0:
        trend='Rising'; factor=1.08
    elif previous == 0:
        trend='Not enough sales'; factor=1.0
    else:
        change=(recent-previous)/previous
        trend='Rising' if change >= .15 else ('Softening' if change <= -.15 else 'Stable')
        factor=1.08 if trend=='Rising' else (.94 if trend=='Softening' else 1.0)

    predicted=round(recent*factor,2) if recent or previous else 0
    stock=d.execute("""SELECT COALESCE(SUM(quantity),0) qty FROM products
        WHERE farmer_id=? AND category=? AND lower(name)=lower(?)""",(farmer_id,category,crop)).fetchone()['qty']
    current_stock=float(stock or 0)
    planned=float(planned_qty or 0)
    total_available=round(current_stock+planned,2)
    gap=round(predicted-total_available,2)

    if predicted <= 0:
        status='Need more sales data'; recommendation='Keep the plan normal until demand data builds.'
    elif gap > 0:
        status='Potential shortage'; recommendation=f'Consider planning about {gap:g} more {unit}.'
    elif total_available > predicted*1.5:
        status='Possible surplus'; recommendation='Consider reducing the planned harvest.'
    else:
        status='Well matched'; recommendation='Your current stock + planned harvest is close to expected demand.'

    return {'trend':trend,'predicted_demand':predicted,'current_stock':current_stock,
            'planned_harvest':planned,'total_available':total_available,'gap':gap,
            'status':status,'recommendation':recommendation}

def supply_demand_matching():
    """Build a simple market-level supply vs demand view from AgriDirect data."""
    d=db()
    categories=rows("SELECT DISTINCT category FROM products WHERE TRIM(category)<>'' ORDER BY category")
    result=[]
    for c in categories:
        category=c['category']
        supply=d.execute('SELECT COALESCE(SUM(quantity),0) qty, COUNT(*) listings FROM products WHERE category=?',(category,)).fetchone()
        recent=d.execute("""SELECT COALESCE(SUM(oi.quantity),0) qty
            FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id
            WHERE p.category=? AND datetime(o.created_at)>=datetime('now','-30 day')""",(category,)).fetchone()['qty']
        previous=d.execute("""SELECT COALESCE(SUM(oi.quantity),0) qty
            FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id
            WHERE p.category=? AND datetime(o.created_at)>=datetime('now','-60 day') AND datetime(o.created_at)<datetime('now','-30 day')""",(category,)).fetchone()['qty']

        if previous == 0 and recent > 0:
            trend='Rising'; demand_score=recent
        elif previous == 0:
            trend='Not enough sales'; demand_score=0
        else:
            change=(recent-previous)/previous
            trend='Rising' if change >= .15 else ('Softening' if change <= -.15 else 'Stable')
            demand_score=round(recent * (1.08 if trend=='Rising' else .94 if trend=='Softening' else 1.0))

        supply_qty=int(supply['qty'] or 0)

        # With no sales history, there is no reliable demand number to compare.
        if demand_score <= 0:
            status='No clear demand'
            icon='ℹ️'
            action='Build sales history'
        elif supply_qty < demand_score * .8:
            status='Shortage'
            icon='🔴'
            action='Grow more'
        elif supply_qty > demand_score * 1.5:
            status='Surplus'
            icon='🟠'
            action='Avoid growing too much'
        else:
            status='Balanced'
            icon='🟢'
            action='Keep production steady'

        result.append({
            'category':category, 'supply':supply['qty'], 'listings':supply['listings'],
            'recent_demand':recent, 'projected_demand':demand_score, 'trend':trend,
            'status':status, 'icon':icon, 'action':action
        })
    return result

@app.route('/farmer/supply-demand')
@require('farmer')
def supply_demand():
    matches=supply_demand_matching()
    return render_template('supply_demand.html', matches=matches)

@app.context_processor
def ctx():
 items=cart_products(); u=user(); unread=0; wishlist_count=0
 if u:
  unread=db().execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0',(u['id'],)).fetchone()[0]
  if u['role']=='consumer':
   wishlist_count=db().execute('SELECT COUNT(*) FROM wishlist WHERE consumer_id=?',(u['id'],)).fetchone()[0]
 return {'current_user':u,'cart_count':sum(q for _,q in items),'unread_notifications':unread,'wishlist_count':wishlist_count,'language':session.get('language','en')}

@app.route('/')
def home():
 u=user()
 if u: return redirect(url_for('farmer_home' if u['role']=='farmer' else 'consumer_home'))
 return render_template('role_login.html')
@app.route('/signup/<role>',methods=['GET','POST'])
def signup(role):
 if role not in ('farmer','consumer'): return ('Not found',404)
 if request.method=='POST':
  name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); pw=request.form.get('password',''); loc=request.form.get('location','').strip() or 'Local area'
  if not name or not email or len(pw)<4: flash('Enter name, email and a password of at least 4 characters.'); return render_template('signup.html',role=role)
  try:
   d=db(); cur=d.execute('INSERT INTO users(name,email,password,role,location) VALUES(?,?,?,?,?)',(name,email,generate_password_hash(pw),role,loc)); d.commit(); lang=session.get('language','en'); session.clear(); session['language']=lang; session['uid']=cur.lastrowid; session['cart']={}
   return redirect(url_for('farmer_home' if role=='farmer' else 'consumer_home'))
  except sqlite3.IntegrityError: flash('This email is already registered.')
 return render_template('signup.html',role=role)
@app.route('/login/<role>',methods=['GET','POST'])
def login(role):
 if role not in ('farmer','consumer'): return ('Not found',404)
 if request.method=='POST':
  u=db().execute('SELECT * FROM users WHERE email=? AND role=?',(request.form.get('email','').strip().lower(),role)).fetchone()
  if u and check_password_hash(u['password'],request.form.get('password','')): lang=session.get('language','en'); session.clear(); session['language']=lang; session['uid']=u['id']; session['cart']={}; return redirect(url_for('farmer_home' if role=='farmer' else 'consumer_home'))
  flash('Invalid email or password.')
 return render_template('login.html',role=role)
@app.route('/set-language/<lang>')
def set_language(lang):
 if lang not in {'en','ta','hi'}: lang='en'
 session['language']=lang
 return redirect(request.referrer or url_for('home'))

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('home'))

@app.route('/farmer')
@require('farmer')
def farmer_home():
 u=user()

 stats = db().execute('''
     SELECT COUNT(*) AS total_products,
            COALESCE(SUM(quantity), 0) AS total_stock
     FROM products WHERE farmer_id=?
 ''', (u['id'],)).fetchone()

 order_stats = db().execute('''
     SELECT COUNT(DISTINCT oi.order_id) AS total_orders,
            COALESCE(SUM(oi.quantity * oi.price), 0) AS total_earnings
     FROM order_items oi
     JOIN orders o ON o.id=oi.order_id
     WHERE oi.farmer_id=?
 ''', (u['id'],)).fetchone()

 ps = rows('SELECT * FROM products WHERE farmer_id=? ORDER BY id DESC',
           (u['id'],))

 # Build Smart Price Advisor data for every product shown on the dashboard.
 advice = {p['id']: price_advice(p) for p in ps}

 # Newest orders are useful dashboard information; detailed alerts live under Messages.
 recent_orders = rows('''
     SELECT o.id, o.status, o.created_at,
            oi.quantity, oi.price,
            p.name AS product_name,
            u.name AS consumer
     FROM order_items oi
     JOIN orders o ON o.id=oi.order_id
     JOIN products p ON p.id=oi.product_id
     JOIN users u ON u.id=o.consumer_id
     WHERE oi.farmer_id=?
     ORDER BY o.id DESC LIMIT 5
 ''', (u['id'],))

 return render_template('farmer.html',
                        products=ps,
                        stats=stats,
                        order_stats=order_stats,
                        recent_orders=recent_orders,
                        advice=advice)
@app.route('/farmer/add',methods=['GET','POST'])
@require('farmer')
def add_produce():
 if request.method=='POST':
  name=request.form.get('name','').strip(); cat=request.form.get('category','Vegetables'); qty=request.form.get('quantity',type=int) or 0; unit=request.form.get('unit','kg'); price=request.form.get('price',type=float) or 0; harvested=request.form.get('harvested','Today')
  if not name or qty<=0 or price<=0: flash('Enter product name, quantity and price.'); return render_template('add_produce.html')
  d=db(); d.execute('INSERT INTO products(farmer_id,name,category,quantity,unit,price,harvested,created_at) VALUES(?,?,?,?,?,?,?,?)',(user()['id'],name,cat,qty,unit,price,harvested,datetime.now().isoformat())); d.commit(); flash('Produce saved and published to consumers.'); return redirect(url_for('farmer_home'))
 return render_template('add_produce.html')
@app.route('/farmer/product/<int:pid>/edit',methods=['GET','POST'])
@require('farmer')
def edit_produce(pid):
 p=db().execute('SELECT * FROM products WHERE id=? AND farmer_id=?',(pid,user()['id'])).fetchone()
 if not p: return ('Not found',404)
 if request.method=='POST':
  name=request.form.get('name','').strip(); cat=request.form.get('category','Vegetables'); qty=request.form.get('quantity',type=int); unit=request.form.get('unit','kg'); price=request.form.get('price',type=float); harvested=request.form.get('harvested','Today')
  if not name or qty is None or qty<0 or price is None or price<=0:
   flash('Enter valid product details.'); return render_template('edit_produce.html',product=p)
  d=db(); d.execute('UPDATE products SET name=?,category=?,quantity=?,unit=?,price=?,harvested=? WHERE id=? AND farmer_id=?',(name,cat,qty,unit,price,harvested,pid,user()['id'])); d.commit(); flash('Produce updated successfully.'); return redirect(url_for('farmer_home'))
 return render_template('edit_produce.html',product=p)

@app.post('/farmer/product/<int:pid>/delete')
@require('farmer')
def delete_produce(pid):
 p=db().execute('SELECT id FROM products WHERE id=? AND farmer_id=?',(pid,user()['id'])).fetchone()
 if not p: return ('Not found',404)
 used=db().execute('SELECT 1 FROM order_items WHERE product_id=? LIMIT 1',(pid,)).fetchone()
 if used:
  flash('This product has order history, so it cannot be deleted. Set its stock to 0 instead.')
 else:
  d=db(); d.execute('DELETE FROM products WHERE id=? AND farmer_id=?',(pid,user()['id'])); d.commit(); flash('Produce deleted.')
 return redirect(url_for('farmer_home'))

@app.post('/farmer/product/<int:pid>/stock')
@require('farmer')
def update_stock(pid):
 qty=request.form.get('quantity',type=int)
 if qty is None or qty<0:
  flash('Stock quantity must be 0 or greater.')
  return redirect(url_for('farmer_home'))
 cur=db().execute('UPDATE products SET quantity=? WHERE id=? AND farmer_id=?',(qty,pid,user()['id']))
 db().commit()
 if cur.rowcount: flash('Stock quantity updated.')
 else: return ('Not found',404)
 return redirect(url_for('farmer_home'))

@app.post('/farmer/order/<int:oid>/status')
@require('farmer')
def update_order_status(oid):
 allowed=['Placed','Confirmed','Packed','Shipped','Delivered']
 status=request.form.get('status','')
 if status not in allowed: flash('Invalid order status.'); return redirect(url_for('farmer_orders'))
 d=db()
 exists=d.execute('SELECT 1 FROM order_items WHERE order_id=? AND farmer_id=?',(oid,user()['id'])).fetchone()
 if not exists: return ('Not found',404)
 d.execute('UPDATE orders SET status=? WHERE id=?',(status,oid))
 consumer=d.execute('SELECT consumer_id FROM orders WHERE id=?',(oid,)).fetchone()['consumer_id']
 d.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(consumer,f'Order #{oid} is now {status}.',datetime.now().isoformat()))
 d.commit(); flash(f'Order #{oid} marked {status}.'); return redirect(url_for('farmer_orders'))

@app.route('/farmer/future-harvest',methods=['GET','POST'])
@require('farmer')
def future_harvest():
    u=user()
    if request.method=='POST':
        crop=request.form.get('crop','').strip(); category=request.form.get('category','Vegetables'); qty=request.form.get('quantity',type=int); unit=request.form.get('unit','kg'); harvest_date=request.form.get('harvest_date','').strip()
        if not crop or qty is None or qty<=0 or not harvest_date:
            flash('Enter crop, quantity and harvest date.')
            return redirect(url_for('future_harvest'))
        a=future_harvest_advice(u['id'],crop,category)
        expected=((a['low']+a['high'])/2) if a['high'] else 0
        d=db(); d.execute('INSERT INTO future_harvests(farmer_id,crop,category,quantity,unit,harvest_date,expected_price,created_at) VALUES(?,?,?,?,?,?,?,?)',(u['id'],crop,category,qty,unit,harvest_date,expected,datetime.now().isoformat())); d.commit(); flash('Future harvest plan saved.')
        return redirect(url_for('future_harvest'))
    plans=rows('SELECT * FROM future_harvests WHERE farmer_id=? ORDER BY harvest_date ASC,id DESC',(u['id'],))
    enriched=[]
    for p in plans:
        a=future_harvest_advice(u['id'],p['crop'],p['category'])
        intel=future_harvest_intelligence(u['id'],p['crop'],p['category'],p['quantity'],p['unit'])
        enriched.append((p,a,intel))
    return render_template('future_harvest.html',plans=enriched)

@app.post('/farmer/future-harvest/<int:hid>/status')
@require('farmer')
def future_harvest_status(hid):
    status=request.form.get('status','')
    if status not in ('Open','Closed'): return ('Invalid status',400)
    cur=db().execute('UPDATE future_harvests SET status=? WHERE id=? AND farmer_id=?',(status,hid,user()['id'])); db().commit()
    if not cur.rowcount: return ('Not found',404)
    flash('Future harvest plan updated.')
    return redirect(url_for('future_harvest'))

@app.route('/farmer/orders')
@require('farmer')
def farmer_orders():
 os=rows('''SELECT o.id,o.status,o.created_at,o.address,oi.quantity,oi.price,p.name,u.name consumer FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id JOIN users u ON u.id=o.consumer_id WHERE oi.farmer_id=? ORDER BY o.id DESC''',(user()['id'],)); return render_template('orders.html',orders=os,role='farmer')

@app.route('/consumer')
@require('consumer')
def consumer_home():
 q=request.args.get('q','').strip(); cat=request.args.get('category','All'); sql='''SELECT p.*,u.name farmer,u.location farmer_location FROM products p JOIN users u ON u.id=p.farmer_id WHERE p.quantity>0'''; args=[]
 if q: sql+=' AND (p.name LIKE ? OR p.category LIKE ? OR u.name LIKE ?)'; args += ['%'+q+'%','%'+q+'%','%'+q+'%']
 if cat!='All': sql+=' AND p.category=?'; args.append(cat)
 sql+=' ORDER BY p.id DESC'
 return render_template('consumer.html',products=rows(sql,args),query=q,category=cat,wishlist_ids=wishlist_ids(user()['id']))

@app.post('/wishlist/toggle/<int:pid>')
@require('consumer')
def toggle_wishlist(pid):
    d=db()
    p=d.execute('SELECT id FROM products WHERE id=?',(pid,)).fetchone()
    if not p:
        return ('Product not found',404)
    existing=d.execute('SELECT id FROM wishlist WHERE consumer_id=? AND product_id=?',(user()['id'],pid)).fetchone()
    if existing:
        d.execute('DELETE FROM wishlist WHERE id=?',(existing['id'],))
        flash('Removed from Wishlist.')
    else:
        d.execute('INSERT OR IGNORE INTO wishlist(consumer_id,product_id,created_at) VALUES(?,?,?)',(user()['id'],pid,datetime.now().isoformat()))
        flash('Added to Wishlist.')
    d.commit()
    return redirect(request.referrer or url_for('consumer_home'))

@app.route('/wishlist')
@require('consumer')
def wishlist():
    items=rows('''SELECT p.*,u.name farmer,u.location farmer_location,
                         COALESCE(AVG(r.rating),0) avg_rating, COUNT(r.id) review_count
                  FROM wishlist w
                  JOIN products p ON p.id=w.product_id
                  JOIN users u ON u.id=p.farmer_id
                  LEFT JOIN reviews r ON r.product_id=p.id
                  WHERE w.consumer_id=?
                  GROUP BY p.id
                  ORDER BY w.id DESC''',(user()['id'],))
    return render_template('wishlist.html',items=items)

@app.post('/reviews/<int:pid>')
@require('consumer')
def submit_review(pid):
    d=db()
    purchased=d.execute('''SELECT 1 FROM orders o
                           JOIN order_items oi ON oi.order_id=o.id
                           WHERE o.consumer_id=? AND oi.product_id=?
                             AND o.status IN ('Placed','Confirmed','Packed','Shipped','Delivered')
                           LIMIT 1''',(user()['id'],pid)).fetchone()
    if not purchased:
        flash('You can review a product only after buying it.')
        return redirect(url_for('consumer_product',pid=pid))
    rating=request.form.get('rating',type=int)
    comment=request.form.get('comment','').strip()
    if rating not in (1,2,3,4,5):
        flash('Please choose a rating from 1 to 5 stars.')
        return redirect(url_for('consumer_product',pid=pid))
    now=datetime.now().isoformat()
    existing=d.execute('SELECT id FROM reviews WHERE consumer_id=? AND product_id=?',(user()['id'],pid)).fetchone()
    if existing:
        d.execute('UPDATE reviews SET rating=?,comment=?,updated_at=? WHERE id=?',(rating,comment,now,existing['id']))
        flash('Your review was updated.')
    else:
        d.execute('INSERT INTO reviews(consumer_id,product_id,rating,comment,created_at,updated_at) VALUES(?,?,?,?,?,?)',(user()['id'],pid,rating,comment,now,now))
        flash('Thanks for your review.')
    d.commit()
    return redirect(url_for('consumer_product',pid=pid))

@app.route('/consumer/product/<int:pid>')
@require('consumer')
def consumer_product(pid):
 d=db()
 product=d.execute('SELECT p.*,u.name farmer,u.location farmer_location FROM products p JOIN users u ON u.id=p.farmer_id WHERE p.id=?',(pid,)).fetchone()
 if not product: return ('Product not found or sold out',404)
 reviews=rows('''SELECT r.*,u.name consumer FROM reviews r
                 JOIN users u ON u.id=r.consumer_id
                 WHERE r.product_id=? ORDER BY r.updated_at DESC''',(pid,))
 rating=d.execute('SELECT COALESCE(AVG(rating),0) avg_rating, COUNT(*) review_count FROM reviews WHERE product_id=?',(pid,)).fetchone()
 purchased=d.execute('''SELECT 1 FROM orders o JOIN order_items oi ON oi.order_id=o.id
                        WHERE o.consumer_id=? AND oi.product_id=? LIMIT 1''',(user()['id'],pid)).fetchone() is not None
 my_review=d.execute('SELECT * FROM reviews WHERE consumer_id=? AND product_id=?',(user()['id'],pid)).fetchone()
 wished=d.execute('SELECT 1 FROM wishlist WHERE consumer_id=? AND product_id=?',(user()['id'],pid)).fetchone() is not None
 return render_template('product.html',product=product,reviews=reviews,rating=rating,purchased=purchased,my_review=my_review,wished=wished)

@app.post('/cart/add/<int:pid>')
@require('consumer')
def add_cart(pid):
 p=db().execute('SELECT id FROM products WHERE id=? AND quantity>0',(pid,)).fetchone()
 if not p: flash('Product is unavailable.'); return redirect(url_for('consumer_home'))
 c=session.get('cart',{}); c[str(pid)]=int(c.get(str(pid),0))+1; session['cart']=c; return redirect(url_for('cart'))
@app.route('/cart')
@require('consumer')
def cart():
 items=cart_products(); total=sum(p['price']*q for p,q in items); return render_template('cart.html',items=items,total=total)
@app.post('/cart/update')
@require('consumer')
def update_cart():
 c={}
 for k,v in request.form.items():
  if k.startswith('q_'):
   try:
    n=int(v)
    if n>0:c[k[2:]]=n
   except: pass
 session['cart']=c; return redirect(url_for('cart'))
@app.route('/checkout',methods=['GET','POST'])
@require('consumer')
def checkout():
 items=cart_products(); total=sum(p['price']*q for p,q in items)
 if not items:return redirect(url_for('consumer_home'))
 if request.method=='POST':
  address=request.form.get('address','').strip()
  method=request.form.get('payment_method','').strip().lower()
  allowed={'cod','upi','card','netbanking'}
  if not address:
   flash('Enter your delivery address.')
   return render_template('checkout.html',items=items,total=total)
  if method not in allowed:
   flash('Select a payment method.')
   return render_template('checkout.html',items=items,total=total)
  # Re-check stock before creating the order.
  for p,q in items:
   if q<=0 or p['quantity'] < q:
    flash(f"Not enough stock for {p['name']}.")
    return render_template('checkout.html',items=items,total=total)
  d=db()
  status='Placed' if method=='cod' else 'Payment Pending'
  cur=d.execute('INSERT INTO orders(consumer_id,total,address,status,created_at) VALUES(?,?,?,?,?)',(user()['id'],total,address,status,datetime.now().isoformat()))
  oid=cur.lastrowid
  farmer_ids=set()
  for p,q in items:
   farmer_ids.add(p['farmer_id'])
   d.execute('INSERT INTO order_items(order_id,product_id,farmer_id,quantity,price) VALUES(?,?,?,?,?)',(oid,p['id'],p['farmer_id'],q,p['price']))
  payment_status='Pending' if method!='cod' else 'Pending'
  d.execute('INSERT INTO payments(order_id,consumer_id,amount,payment_method,status,created_at) VALUES(?,?,?,?,?,?)',(oid,user()['id'],total,method,payment_status,datetime.now().isoformat()))
  if method=='cod':
   # Re-check and decrement stock inside the same transaction so two buyers
   # cannot both successfully place an order for the last units.
   for p,q in items:
    changed=d.execute('UPDATE products SET quantity=quantity-? WHERE id=? AND quantity>=?',(q,p['id'],q))
    if changed.rowcount != 1:
     d.rollback()
     flash(f'Not enough stock for {p["name"]}. Your order was not placed.')
     return redirect(url_for('cart'))
   for fid in farmer_ids:
    d.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(fid,f'New order #{oid} received (Cash on Delivery).',datetime.now().isoformat()))
   d.commit(); session['cart']={}
   return redirect(url_for('order_success',oid=oid))
  d.commit()
  session['pending_payment_order']=oid
  return redirect(url_for('payment',oid=oid))
 return render_template('checkout.html',items=items,total=total)

@app.route('/payment/<int:oid>',methods=['GET','POST'])
@require('consumer')
def payment(oid):
 d=db()
 order=d.execute('SELECT * FROM orders WHERE id=? AND consumer_id=?',(oid,user()['id'])).fetchone()
 pay=d.execute('SELECT * FROM payments WHERE order_id=? AND consumer_id=? ORDER BY id DESC LIMIT 1',(oid,user()['id'])).fetchone()
 if not order or not pay:
  flash('Payment session not found.')
  return redirect(url_for('consumer_orders'))
 if pay['status']=='Paid':
  return redirect(url_for('order_success',oid=oid))
 if request.method=='POST':
  result=request.form.get('result','success')
  if result not in {'success','failed'}: result='failed'
  if result=='failed':
   d.execute("UPDATE payments SET status='Failed' WHERE id=?",(pay['id'],))
   d.execute("UPDATE orders SET status='Payment Failed' WHERE id=?",(oid,))
   d.commit()
   session.pop('pending_payment_order',None)
   flash('Payment failed. Your stock was not reduced.')
   return redirect(url_for('payment',oid=oid))
  # Mock gateway success: generate a demo transaction ID. No card/UPI credentials are stored.
  transaction_id=f"AGRIDIRECT-{oid}-{int(datetime.now().timestamp())}"
  farmer_ids=set(r['farmer_id'] for r in d.execute('SELECT farmer_id FROM order_items WHERE order_id=?',(oid,)).fetchall())
  for item in d.execute('SELECT product_id,quantity FROM order_items WHERE order_id=?',(oid,)).fetchall():
   changed=d.execute('UPDATE products SET quantity=quantity-? WHERE id=? AND quantity>=?',(item['quantity'],item['product_id'],item['quantity']))
   if changed.rowcount != 1:
    d.rollback()
    d.execute("UPDATE payments SET status='Failed' WHERE id=?",(pay['id'],))
    d.execute("UPDATE orders SET status='Payment Failed' WHERE id=?",(oid,))
    d.commit()
    session.pop('pending_payment_order',None)
    flash('Payment completed but stock changed before confirmation. Please contact support.')
    return redirect(url_for('consumer_orders'))
  d.execute("UPDATE payments SET status='Paid',transaction_id=?,paid_at=? WHERE id=?",(transaction_id,datetime.now().isoformat(),pay['id']))
  d.execute("UPDATE orders SET status='Placed' WHERE id=?",(oid,))
  for fid in farmer_ids:
   d.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(fid,f'New paid order #{oid} received.',datetime.now().isoformat()))
  d.commit(); session.pop('pending_payment_order',None); session['cart']={}
  return redirect(url_for('order_success',oid=oid))
 return render_template('payment.html',order=order,payment=pay)

@app.route('/payment-retry/<int:oid>')
@require('consumer')
def payment_retry(oid):
 d=db(); order=d.execute('SELECT * FROM orders WHERE id=? AND consumer_id=?',(oid,user()['id'])).fetchone()
 pay=d.execute('SELECT * FROM payments WHERE order_id=? AND consumer_id=? ORDER BY id DESC LIMIT 1',(oid,user()['id'])).fetchone()
 if not order or not pay or pay['status']!='Failed': return redirect(url_for('consumer_orders'))
 d.execute("UPDATE payments SET status='Pending',transaction_id=NULL WHERE id=?",(pay['id'],))
 d.execute("UPDATE orders SET status='Payment Pending' WHERE id=?",(oid,)); d.commit()
 return redirect(url_for('payment',oid=oid))

@app.route('/orders')
@require('consumer')
def consumer_orders():
 os=rows('''SELECT o.*,GROUP_CONCAT(p.name || ' x' || oi.quantity, ', ') items FROM orders o JOIN order_items oi ON oi.order_id=o.id JOIN products p ON p.id=oi.product_id WHERE o.consumer_id=? GROUP BY o.id ORDER BY o.id DESC''',(user()['id'],)); return render_template('orders.html',orders=os,role='consumer')

@app.route('/farmer/alerts')
@require('farmer')
def farmer_alerts():
    ps=rows('SELECT * FROM products WHERE farmer_id=? ORDER BY id DESC',(user()['id'],))
    advice={p['id']:price_advice(p) for p in ps}; alerts=[]
    for p in ps:
        a=advice[p['id']]
        if p['quantity']==0: alerts.append({'type':'danger','icon':'🚨','title':'Stock finished','message':f"{p['name']} is sold out.",'action':'Add stock'})
        elif p['quantity']<=5: alerts.append({'type':'warning','icon':'⚠️','title':'Low stock','message':f"{p['name']}: only {p['quantity']} {p['unit']} left.",'action':'Add stock'})
        if a['trend']=='Rising': alerts.append({'type':'good','icon':'🔥','title':'High demand','message':f"{p['name']} is getting more demand.",'action':'Keep stock ready'})
    return render_template('notifications.html',notifications=[],alerts=alerts[:20],alert_tab=True)

@app.route('/notifications')
@require('farmer')
def farmer_notifications():
 d=db(); ns=rows('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 30',(user()['id'],)); d.execute('UPDATE notifications SET read=1 WHERE user_id=?',(user()['id'],)); d.commit(); return render_template('notifications.html',notifications=ns,alerts=[],alert_tab=False)

@app.route('/consumer/notifications')
@require('consumer')
def consumer_notifications():
 d=db(); ns=rows('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 30',(user()['id'],)); d.execute('UPDATE notifications SET read=1 WHERE user_id=?',(user()['id'],)); d.commit(); return render_template('notifications.html',notifications=ns)
@app.post('/voice-chat')
def voice_chat():
    """Small browser voice assistant. No audio or sensitive credentials are stored."""
    u=user()
    data=request.get_json(silent=True) or {}
    text=(data.get('text') or '').strip()
    lang=(data.get('language') or session.get('language','en')).lower()
    if lang not in ('en','ta','hi'): lang='en'
    if not text:
        return {'reply': {'en':'I did not hear anything. Please try again.','ta':'எதுவும் கேட்கவில்லை. மீண்டும் முயற்சிக்கவும்.','hi':'मुझे कुछ सुनाई नहीं दिया। फिर से कोशिश करें.'}[lang]}
    t=text.lower()
    url=None
    reply=None
    if lang=='ta':
        replies={
          'help':'நான் கடை, கூடை, ஆர்டர்கள், விருப்பப்பட்டியல் மற்றும் அறிவிப்புகளைத் திறக்க உதவ முடியும்.',
          'shop':'கடையைத் திறக்கிறேன்.', 'orders':'உங்கள் ஆர்டர்களைத் திறக்கிறேன்.', 'cart':'உங்கள் கூடையைத் திறக்கிறேன்.',
          'wishlist':'உங்கள் விருப்பப்பட்டியலைத் திறக்கிறேன்.', 'notifications':'உங்கள் அறிவிப்புகளைத் திறக்கிறேன்.',
          'farmer':'விவசாயி முகப்பைத் திறக்கிறேன்.', 'future':'எதிர்கால அறுவடை திட்டத்தைத் திறக்கிறேன்.',
          'supply':'வழங்கல் மற்றும் தேவைப் பக்கத்தைத் திறக்கிறேன்.',
          'not_logged':'முதலில் உள்நுழையுங்கள்.'
        }
    elif lang=='hi':
        replies={
          'help':'मैं दुकान, टोकरी, ऑर्डर, पसंदीदा और सूचनाएँ खोलने में मदद कर सकता हूँ.',
          'shop':'मैं दुकान खोल रहा हूँ।', 'orders':'मैं आपके ऑर्डर खोल रहा हूँ।', 'cart':'मैं आपकी टोकरी खोल रहा हूँ।',
          'wishlist':'मैं आपकी पसंद सूची खोल रहा हूँ।', 'notifications':'मैं आपकी सूचनाएँ खोल रहा हूँ।',
          'farmer':'मैं किसान होम खोल रहा हूँ।', 'future':'मैं भविष्य की फसल योजना खोल रहा हूँ।',
          'supply':'मैं आपूर्ति और मांग पेज खोल रहा हूँ।',
          'not_logged':'कृपया पहले लॉग इन करें।'
        }
    else:
        replies={
          'help':'I can help open the shop, basket, orders, wishlist, notifications, and farmer tools.',
          'shop':'Opening the shop.', 'orders':'Opening your orders.', 'cart':'Opening your basket.',
          'wishlist':'Opening your wishlist.', 'notifications':'Opening your notifications.',
          'farmer':'Opening the farmer home.', 'future':'Opening future harvest planning.',
          'supply':'Opening supply and demand.', 'not_logged':'Please log in first.'
        }
    if not u:
        reply=replies['not_logged']
    elif any(x in t for x in ['help','what can you do','என்ன செய்ய','உதவி','क्या कर सकते','मदद']):
        reply=replies['help']
    elif u['role']=='consumer' and any(x in t for x in ['shop','market','products','produce','கடை','பொருள்','சந்தை','दुकान','उत्पाद','बाज़ार']):
        reply=replies['shop']; url=url_for('consumer_home')
    elif any(x in t for x in ['order','orders','ஆர்டர்','ऑर्डर']):
        reply=replies['orders']; url=url_for('consumer_orders' if u['role']=='consumer' else 'farmer_orders')
    elif u['role']=='consumer' and any(x in t for x in ['cart','basket','கூடை','टोकरी']):
        reply=replies['cart']; url=url_for('cart')
    elif u['role']=='consumer' and any(x in t for x in ['wishlist','saved','விருப்ப','पसंद']):
        reply=replies['wishlist']; url=url_for('wishlist')
    elif any(x in t for x in ['notification','alert','அறிவிப்பு','सूचना']):
        reply=replies['notifications']; url=url_for('consumer_notifications' if u['role']=='consumer' else 'farmer_notifications')
    elif u['role']=='farmer' and any(x in t for x in ['future','harvest','அறுவடை','எதிர்கால','फसल','भविष्य']):
        reply=replies['future']; url=url_for('future_harvest')
    elif u['role']=='farmer' and any(x in t for x in ['supply','demand','வழங்கல்','தேவை','आपूर्ति','मांग']):
        reply=replies['supply']; url=url_for('supply_demand')
    elif u['role']=='farmer':
        reply=replies['farmer']; url=url_for('farmer_home')
    else:
        reply=replies['shop']; url=url_for('consumer_home')
    return {'reply':reply,'url':url}

@app.route('/order-success/<int:oid>')
@require('consumer')
def order_success(oid):
 d=db(); payment=d.execute('SELECT * FROM payments WHERE order_id=? AND consumer_id=? ORDER BY id DESC LIMIT 1',(oid,user()['id'])).fetchone()
 return render_template('success.html',order_id=oid,payment=payment)
if __name__=='__main__': app.run(debug=True)
