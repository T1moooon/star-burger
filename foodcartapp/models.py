from collections import defaultdict

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db.models import (
    Sum,
    F,
    DecimalField,
    ExpressionWrapper,
    Value
    )
from django.db.models.functions import Coalesce
from phonenumber_field.modelfields import PhoneNumberField
from geopy import distance

from geo.models import Location
from geo.utils import get_or_create_location


class Restaurant(models.Model):
    name = models.CharField(
        'название',
        max_length=50
    )
    address = models.CharField(
        'адрес',
        max_length=100,
        blank=True,
    )
    contact_phone = models.CharField(
        'контактный телефон',
        max_length=50,
        blank=True,
    )

    class Meta:
        verbose_name = 'ресторан'
        verbose_name_plural = 'рестораны'

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def available(self):
        products = (
            RestaurantMenuItem.objects
            .filter(availability=True)
            .values_list('product')
        )
        return self.filter(pk__in=products)


class ProductCategory(models.Model):
    name = models.CharField(
        'название',
        max_length=50
    )

    class Meta:
        verbose_name = 'категория'
        verbose_name_plural = 'категории'

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(
        'название',
        max_length=50
    )
    category = models.ForeignKey(
        ProductCategory,
        verbose_name='категория',
        related_name='products',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    price = models.DecimalField(
        'цена',
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    image = models.ImageField(
        'картинка'
    )
    special_status = models.BooleanField(
        'спец.предложение',
        default=False,
        db_index=True,
    )
    description = models.TextField(
        'описание',
        max_length=200,
        blank=True,
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = 'товар'
        verbose_name_plural = 'товары'

    def __str__(self):
        return self.name


class RestaurantMenuItem(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        related_name='menu_items',
        verbose_name="ресторан",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='menu_items',
        verbose_name='продукт',
    )
    availability = models.BooleanField(
        'в продаже',
        default=True,
        db_index=True
    )

    class Meta:
        verbose_name = 'пункт меню ресторана'
        verbose_name_plural = 'пункты меню ресторана'
        unique_together = [
            ['restaurant', 'product']
        ]

    def __str__(self):
        return f"{self.restaurant.name} - {self.product.name}"


class OrderQuerySet(models.QuerySet):
    def with_total_cost(self):
        position_sum = ExpressionWrapper(
            F('items__quantity') * F('items__product__price'),
            output_field=DecimalField(max_digits=8, decimal_places=2),
        )
        return self.annotate(
            total_cost=Coalesce(
                Sum(position_sum),
                Value(0, output_field=DecimalField(max_digits=8, decimal_places=2))
            )
        )

    def with_available_restaurants(self):
        orders = list(self)
        if not orders:
            return orders

        restaurants = Restaurant.objects.all()

        restaurant_addresses = [restaurant.address.strip() for restaurant in restaurants]
        order_addresses = [order.address.strip() for order in orders]
        all_addresses = list(set(restaurant_addresses + order_addresses))

        locations = Location.objects.filter(address__in=all_addresses)
        location_by_address = {
            location.address.strip(): (float(location.latitude), float(location.longitude))
            for location in locations if location.latitude and location.longitude
        }

        for address in all_addresses:
            if not address or address in location_by_address:
                continue

            location = get_or_create_location(address)
            if location and location.latitude and location.longitude:
                location_by_address[address] = (
                    float(location.latitude), float(location.longitude)
                )

        restaurant_coords = {}
        for restaurant in restaurants:
            coords = location_by_address.get(restaurant.address.strip())
            if coords:
                restaurant_coords[restaurant.id] = coords

        menu_items = (
            RestaurantMenuItem.objects
            .filter(availability=True)
            .values('product_id', 'restaurant_id')
        )

        product_to_restaurants = defaultdict(list)
        for item in menu_items:
            product_to_restaurants[item['product_id']].append(item['restaurant_id'])

        restaurants_by_id = Restaurant.objects.in_bulk()

        for order in orders:
            product_ids = [item.product.id for item in order.items.all()]
            restaurant_sets = [
                set(product_to_restaurants.get(product_id, ()))
                for product_id in product_ids
            ]
            common_restaurants = (
                set.intersection(*restaurant_sets)
                if restaurant_sets else set()
            )

            if common_restaurants:
                order.available_restaurants = [
                    restaurants_by_id[restaurant_id]
                    for restaurant_id in common_restaurants
                ]

                order_coord = location_by_address.get(order.address.strip())
                if order_coord:
                    distances = []
                    for restaurant in order.available_restaurants:
                        restaurant_coord = restaurant_coords.get(restaurant.id)
                        if restaurant_coord:
                            dist = round(distance.distance(order_coord, restaurant_coord).km, 2)
                            distances.append((restaurant, dist))
                        else:
                            distances.append((restaurant, None))
                    order.distances = sorted(
                        distances,
                        key=lambda x: (x[1] is None, x[1])
                    )
                else:
                    order.distances = [(restaurant, None) for restaurant in order.available_restaurants]
            else:
                order.available_restaurants = []
                order.distances = []

        return orders


class Order(models.Model):
    STATUS_CHOICES = [
        ('raw', 'Необработанный'),
        ('inprogress', 'В работе'),
        ('delivery', 'Доставка'),
        ('completed', 'Завершен'),
    ]
    PAYMENTS = [
        ('cash', 'Наличностью'),
        ('electronic', 'Электронно')
    ]
    firstname = models.CharField('Имя', max_length=150)
    lastname = models.CharField('Фамилия', max_length=150)
    phonenumber = PhoneNumberField('Телефон', db_index=True)
    address = models.CharField('Адрес', max_length=255)
    comment = models.TextField('Комментарий', blank=True)
    created_at = models.DateTimeField('Дата оформления', default=timezone.now, db_index=True)
    called_at = models.DateTimeField('Дата звонка', blank=True, null=True, db_index=True)
    delivered_at = models.DateTimeField('Дата доставки', blank=True, null=True, db_index=True)
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=STATUS_CHOICES,
        default='raw',
        db_index=True
    )
    payment_type = models.CharField(
        'Способ оплаты',
        max_length=20,
        choices=PAYMENTS,
        db_index=True
    )
    restaurant = models.ForeignKey(
        Restaurant,
        verbose_name='Ресторан',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='orders'
    )

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    def __str__(self):
        return f'{self.lastname} {self.firstname}, {self.address}'


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        related_name='items',
        on_delete=models.CASCADE
        )
    product = models.ForeignKey(
        Product,
        related_name='order_items',
        on_delete=models.PROTECT
        )
    quantity = models.PositiveIntegerField(
        'Количество',
        validators=[MinValueValidator(1)],
        default=1
        )
    price = models.DecimalField(
        'Цена позиции',
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказа'

    def __str__(self):
        return f'{self.product.name} x{self.quantity} по {self.price}'
