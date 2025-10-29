from collections import defaultdict

from geopy import distance
from django import forms
from django.shortcuts import redirect, render
from django.views import View
from django.urls import reverse_lazy
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth import authenticate, login
from django.contrib.auth import views as auth_views


from foodcartapp.models import Product, Restaurant, Order, RestaurantMenuItem
from geo.models import Location
from geo.utils import get_or_create_location


class Login(forms.Form):
    username = forms.CharField(
        label='Логин', max_length=75, required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Укажите имя пользователя'
        })
    )
    password = forms.CharField(
        label='Пароль', max_length=75, required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль'
        })
    )


class LoginView(View):
    def get(self, request, *args, **kwargs):
        form = Login()
        return render(request, "login.html", context={
            'form': form
        })

    def post(self, request):
        form = Login(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                if user.is_staff:  # FIXME replace with specific permission
                    return redirect("restaurateur:RestaurantView")
                return redirect("start_page")

        return render(request, "login.html", context={
            'form': form,
            'ivalid': True,
        })


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy('restaurateur:login')


def is_manager(user):
    return user.is_staff  # FIXME replace with specific permission


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_products(request):
    restaurants = list(Restaurant.objects.order_by('name'))
    products = list(Product.objects.prefetch_related('menu_items'))

    products_with_restaurant_availability = []
    for product in products:
        availability = {item.restaurant_id: item.availability for item in product.menu_items.all()}
        ordered_availability = [availability.get(restaurant.id, False) for restaurant in restaurants]

        products_with_restaurant_availability.append(
            (product, ordered_availability)
        )

    return render(request, template_name="products_list.html", context={
        'products_with_restaurant_availability': products_with_restaurant_availability,
        'restaurants': restaurants,
    })


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_restaurants(request):
    return render(request, template_name="restaurants_list.html", context={
        'restaurants': Restaurant.objects.all(),
    })


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_orders(request):
    orders = (
        Order.objects
        .exclude(status__in=['completed'])
        .select_related('restaurant')
        .prefetch_related('items__product')
        .order_by('-status')
        .with_total_cost()
    )
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

    restaurants = Restaurant.objects.in_bulk()

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
                restaurants[restaurant_id]
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
    return render(request, 'order_items.html', {'orders': orders})
