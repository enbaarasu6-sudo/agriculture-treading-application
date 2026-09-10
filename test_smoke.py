from app import app, DB
import shutil

BACKUP = DB + '.smoke_backup'
shutil.copy2(DB, BACKUP)
try:
    client = app.test_client()

    assert client.get('/').status_code == 200
    assert client.get('/login/farmer').status_code == 200
    assert client.get('/login/consumer').status_code == 200

    assert client.get('/farmer').status_code == 302
    assert client.get('/consumer').status_code == 302

    with client:
        response = client.post('/login/farmer', data={
            'email': 'farmer@agridirect.com', 'password': 'farmer123'
        })
        assert response.status_code == 302 and '/farmer' in response.location
        assert client.get('/farmer').status_code == 200
        assert client.get('/consumer').status_code == 302
        assert client.get('/farmer/supply-demand').status_code == 200
        assert client.get('/farmer/future-harvest').status_code == 200
        assert client.get('/farmer/alerts').status_code == 200
        client.get('/logout')

    with client:
        response = client.post('/login/consumer', data={
            'email': 'consumer@agridirect.com', 'password': 'consumer123'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Good food starts' in response.data

        assert client.get('/wishlist').status_code == 200
        assert client.get('/consumer/notifications').status_code == 200
        assert client.get('/consumer/product/1').status_code == 200

        # Add a small quantity and exercise COD checkout.
        response = client.post('/cart/add/1', follow_redirects=True)
        assert response.status_code == 200
        response = client.post('/checkout', data={
            'payment_method': 'cod', 'address': 'Demo'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Order confirmed' in response.data
        assert client.get('/orders').status_code == 200
        client.get('/logout')

    print('AgriDirect smoke tests passed')
finally:
    # Restore the exact demo database even if a test fails.
    shutil.copy2(BACKUP, DB)
    import os
    os.remove(BACKUP)
