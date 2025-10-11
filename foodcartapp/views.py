import json

from django.http import JsonResponse
from django.templatetags.static import static
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Product
from .models import Order
from .models import OrderItem


def banners_list_api(request):
    # FIXME move data to db?
    return JsonResponse([
        {
            'title': 'Burger',
            'src': static('burger.jpg'),
            'text': 'Tasty Burger at your door step',
        },
        {
            'title': 'Spices',
            'src': static('food.jpg'),
            'text': 'All Cuisines',
        },
        {
            'title': 'New York',
            'src': static('tasty.jpg'),
            'text': 'Food is incomplete without a tasty dessert',
        }
    ], safe=False, json_dumps_params={
        'ensure_ascii': False,
        'indent': 4,
    })


def product_list_api(request):
    products = Product.objects.select_related('category').available()

    dumped_products = []
    for product in products:
        dumped_product = {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'special_status': product.special_status,
            'description': product.description,
            'category': {
                'id': product.category.id,
                'name': product.category.name,
            } if product.category else None,
            'image': product.image.url,
            'restaurant': {
                'id': product.id,
                'name': product.name,
            }
        }
        dumped_products.append(dumped_product)
    return JsonResponse(dumped_products, safe=False, json_dumps_params={
        'ensure_ascii': False,
        'indent': 4,
    })


@api_view(['POST'])
def register_order(request):
    order = request.data

    if 'products' not in order:
        return Response(
            {'error': 'products: Обязательное поле.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    elif order['products'] is None:
        return Response(
            {'error': 'products: Это поле не может быть пустым.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    elif not order['products']:
        return Response(
            {'error': 'products: Этот список не может быть пустым.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    elif not isinstance(order['products'], list):
        return Response(
            {'error': 'products: Ожидался list со значениями, но был получен "str".'},
            status=status.HTTP_400_BAD_REQUEST
        )

    create_order = Order.objects.create(
        first_name=order['firstname'],
        last_name=order['lastname'],
        phone=order['phonenumber'],
        address=order['address'],
    )

    for item in order['products']:
        product = Product.objects.get(pk=item['product'])
        OrderItem.objects.create(
            order=create_order,
            product=product,
            quantity=item.get('quantity', 1),
        )
    return JsonResponse({})
