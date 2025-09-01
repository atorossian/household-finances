
from enum import Enum


class EntryType(str, Enum):
    income = "income"
    expense = "expense"


class Category(str, Enum):
    salary = "salary"
    rent = "rent"
    groceries = "groceries"
    vehicles = "vehicles"
    transport = "transport"
    clothing = "clothing"
    trips = "trips"
    home = "home"
    investment = "investment"
    financing = "financing"
    health = "health"
    entertainment = "entertainment"
    subscriptions = "subscriptions"
    restaurants = "restaurants"
    bills = "bills"
    extraordinary_expenses = "extraordinary_expenses"
    extraordinary_incomes = "extraordinary_incomes"
    academic = "academic"
    presents = "presents"
    vehicles = "vehicles"
    other = "other"
