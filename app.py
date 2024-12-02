from flask import Flask, render_template, redirect, url_for, request, flash, session
from models import db, Producto, Venta, DetalleVenta
from forms import ProductoForm
from datetime import datetime
import matplotlib
matplotlib.use('Agg')  # Forzar el backend no interactivo
import matplotlib.pyplot as plt
import os
import pandas as pd
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurar el logging para capturar errores
logging.basicConfig(level=logging.DEBUG)

db.init_app(app)

# Crear las tablas si no existen
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

# Rutas para el Inventario
@app.route('/inventario', methods=['GET', 'POST'])
def inventario():
    form = ProductoForm()
    if form.validate_on_submit():
        nuevo_producto = Producto(
            nombre=form.nombre.data,
            precio=form.precio.data,
            cantidad=form.cantidad.data
        )
        db.session.add(nuevo_producto)
        db.session.commit()
        flash('Producto añadido al inventario!', 'success')
        return redirect(url_for('inventario'))
    productos = Producto.query.all()
    return render_template('inventory.html', form=form, productos=productos)

# Rutas para las Ventas (Ahora con carrito de compras)
@app.route('/ventas', methods=['GET', 'POST'])
def ventas():
    if 'cart' not in session:
        session['cart'] = []

    productos = Producto.query.all()
    cart = session['cart']

    if request.method == 'POST':
        producto_id = int(request.form.get('producto_id'))
        cantidad = int(request.form.get('cantidad'))

        producto = Producto.query.get(producto_id)
        if producto:
            # Verificar si el producto ya está en el carrito
            found = False
            for item in cart:
                if item['producto_id'] == producto_id:
                    item['cantidad'] += cantidad
                    found = True
                    break
            if not found:
                cart.append({'producto_id': producto_id, 'cantidad': cantidad})
            session['cart'] = cart
            flash('Producto añadido al carrito!', 'success')
        else:
            flash('Producto no encontrado.', 'danger')
        return redirect(url_for('ventas'))

    # Preparar los datos del carrito con información completa del producto
    cart_items = []
    total = 0
    for item in cart:
        producto = Producto.query.get(item['producto_id'])
        if producto:
            subtotal = producto.precio * item['cantidad']
            cart_items.append({
                'producto_id': producto.id,
                'nombre': producto.nombre,
                'precio': producto.precio,
                'cantidad': item['cantidad'],
                'subtotal': subtotal
            })
            total += subtotal

    # Consultar las ventas recientes para pasarlas al template
    ventas_recientes = Venta.query.order_by(Venta.fecha.desc()).limit(10).all()

    return render_template('sales.html', productos=productos, cart=cart_items, total=total, ventas_recientes=ventas_recientes)

@app.route('/remove_from_cart/<int:producto_id>')
def remove_from_cart(producto_id):
    if 'cart' in session:
        cart = session['cart']
        cart = [item for item in cart if item['producto_id'] != producto_id]
        session['cart'] = cart
        flash('Producto eliminado del carrito.', 'success')
    return redirect(url_for('ventas'))

@app.route('/finalizar_venta', methods=['POST'])
def finalizar_venta():
    if 'cart' not in session or not session['cart']:
        flash('El carrito está vacío.', 'warning')
        return redirect(url_for('ventas'))

    cart = session['cart']
    total = 0
    detalles = []

    # Verificar disponibilidad y calcular total
    for item in cart:
        producto = Producto.query.get(item['producto_id'])
        if producto:
            if producto.cantidad < item['cantidad']:
                flash(f'Cantidad insuficiente para el producto {producto.nombre}.', 'danger')
                return redirect(url_for('ventas'))
            subtotal = producto.precio * item['cantidad']
            total += subtotal
            detalles.append({'producto': producto, 'cantidad': item['cantidad'], 'subtotal': subtotal})
        else:
            flash('Producto no encontrado en el carrito.', 'danger')
            return redirect(url_for('ventas'))

    # Crear la venta
    venta = Venta(total=total)
    db.session.add(venta)
    db.session.commit()

    # Crear detalles de venta y actualizar inventario
    for detalle in detalles:
        venta_detalle = DetalleVenta(
            venta_id=venta.id,
            producto_id=detalle['producto'].id,
            cantidad=detalle['cantidad'],
            subtotal=detalle['subtotal']
        )
        db.session.add(venta_detalle)
        # Actualizar el inventario
        detalle['producto'].cantidad -= detalle['cantidad']
    db.session.commit()

    # Vaciar el carrito
    session['cart'] = []
    flash('Venta procesada exitosamente!', 'success')
    return redirect(url_for('ventas'))

# Ruta para los Gráficos
@app.route('/graficos')
def graficos():
    try:
        ventas = Venta.query.all()
        data = []
        for venta in ventas:
            for detalle in venta.detalles:
                data.append({
                    'fecha': venta.fecha.strftime('%Y-%m-%d'),
                    'producto': detalle.producto.nombre,
                    'cantidad': detalle.cantidad,
                    'total': detalle.subtotal
                })
        df = pd.DataFrame(data)
        graph_path = None
        if not df.empty:
            ventas_por_dia = df.groupby('fecha')['total'].sum().reset_index()
            plt.figure(figsize=(10,6))
            plt.plot(ventas_por_dia['fecha'], ventas_por_dia['total'], marker='o', linestyle='-')
            plt.title('Ventas Diarias')
            plt.xlabel('Fecha')
            plt.ylabel('Total de Ventas')
            plt.xticks(rotation=45)
            plt.tight_layout()
            graphs_dir = os.path.join(app.root_path, 'static', 'graphs')
            if not os.path.exists(graphs_dir):
                os.makedirs(graphs_dir)
            graph_filename = 'ventas_diarias.png'
            graph_full_path = os.path.join(graphs_dir, graph_filename)
            plt.savefig(graph_full_path)
            plt.close()
            graph_path = os.path.join('graphs', graph_filename)
        return render_template('charts.html', graph_image=graph_path)
    except Exception as e:
        app.logger.error(f"Error al generar gráficos: {e}")
        flash('Ocurrió un error al generar los gráficos.', 'danger')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
