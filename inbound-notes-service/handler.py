import json
import boto3
import requests
from decimal import Decimal
from uuid import uuid4
from datetime import datetime
from decouple import config

# Configuración DynamoDB
AWS_REGION = "us-east-1"
DYNAMO_TABLE = config("DYNAMO_TABLE")
PRODUCTS_API_URL = config("PRODUCTS_API_URL")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMO_TABLE)


def decimal_to_serializable(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    if isinstance(obj, list):
        return [decimal_to_serializable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: decimal_to_serializable(v) for k, v in obj.items()}
    return obj


def create_inbound_note(event, context):
    body = json.loads(event["body"])
    note_id = str(uuid4())
    date = body["Date"]
    products = body["Products"]

    # Validar formato de productos
    for product in products:
        if "ProductID" not in product or "Quantity" not in product:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Invalid product format"}),
            }
        if product["Quantity"] <= 0:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": f"Invalid quantity for product {product['ProductID']}. Quantity must be greater than 0."}),
            }

    # Llamar al endpoint de productos para actualizar cada producto
    for product in products:
        response = requests.put(
            f"{PRODUCTS_API_URL}/{product['ProductID']}",
            json={"Quantity": product["Quantity"]},
        )
        if response.status_code != 200:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": f"Failed to update product {product['ProductID']}: {response.text}"}),
            }

    # Guardar la nota en DynamoDB
    note = {"NoteID": note_id, "Date": date, "Products": products}
    table.put_item(Item=note)

    return {"statusCode": 201, "body": json.dumps({"message": "Inbound note created", "NoteID": note_id})}


def get_all_inbound_notes(event, context):
    response = table.scan()
    items = decimal_to_serializable(response["Items"])
    return {"statusCode": 200, "body": json.dumps(items)}


def get_inbound_note(event, context):
    note_id = event["pathParameters"]["note_id"]
    response = table.get_item(Key={"NoteID": note_id})
    if "Item" not in response:
        return {"statusCode": 404, "body": json.dumps({"message": "Note not found"})}
    note = decimal_to_serializable(response["Item"])
    return {"statusCode": 200, "body": json.dumps(note)}


def update_inbound_note(event, context):
    note_id = event["pathParameters"]["note_id"]

    # Obtener la nota actual de DynamoDB
    response = table.get_item(Key={"NoteID": note_id})
    if "Item" not in response:
        return {"statusCode": 404, "body": json.dumps({"message": "Note not found"})}
    current_note = response["Item"]

    body = json.loads(event["body"])

    # Validar formato de productos en los nuevos datos
    new_products = body.get("Products", [])
    for product in new_products:
        if "ProductID" not in product or "Quantity" not in product:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Invalid product format"}),
            }
        if product["Quantity"] <= 0:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": f"Invalid quantity for product {product['ProductID']}. Quantity must be greater than 0."}),
            }

    # Crear diccionarios de productos antiguos y nuevos
    old_products = {p["ProductID"]: p for p in current_note.get("Products", [])}
    new_products_dict = {p["ProductID"]: p for p in new_products}

    # Obtener todos los IDs de productos involucrados
    all_product_ids = set(old_products.keys()).union(new_products_dict.keys())

    # Calcular diferencias en cantidades
    for product_id in all_product_ids:
        old_quantity = old_products.get(product_id, {}).get("Quantity", 0)
        new_quantity = new_products_dict.get(product_id, {}).get("Quantity", 0)
        quantity_diff = new_quantity - old_quantity

        if quantity_diff != 0:
            response = requests.put(
                f"{PRODUCTS_API_URL}/{product_id}",
                json={"Quantity": quantity_diff},
            )
            if response.status_code != 200:
                return {
                    "statusCode": 400,
                    "body": json.dumps(
                        {
                            "message": f"Failed to update product {product_id}: {response.text}"
                        }
                    ),
                }

    # Actualizar la nota en DynamoDB
    update_expression = "SET "
    expression_attribute_names = {}
    expression_attribute_values = {}

    for key, value in body.items():
        # Usar alias para nombres de atributos
        alias_key = f"#{key}"  # Siempre usar alias
        update_expression += f"{alias_key} = :{key}, "
        expression_attribute_names[alias_key] = key
        expression_attribute_values[f":{key}"] = value

    update_expression = update_expression.rstrip(", ")

    table.update_item(
        Key={"NoteID": note_id},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values,
        ExpressionAttributeNames=expression_attribute_names,
    )

    return {"statusCode": 200, "body": json.dumps({"message": "Inbound note updated"})}


def delete_inbound_note(event, context):
    note_id = event["pathParameters"]["note_id"]

    response = table.get_item(Key={"NoteID": note_id})
    if "Item" not in response:
        return {"statusCode": 404, "body": json.dumps({"message": "Note not found"})}

    note = response["Item"]

    # Llamar al endpoint de productos para revertir las cantidades
    for product in note["Products"]:
        response = requests.put(
            f"{PRODUCTS_API_URL}/{product['ProductID']}",
            json={"Quantity": -product["Quantity"]},
        )
        if response.status_code != 200:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": f"Failed to revert product {product['ProductID']}: {response.text}"}),
            }

    # Eliminar la nota de DynamoDB
    table.delete_item(Key={"NoteID": note_id})
    return {"statusCode": 200, "body": json.dumps({"message": "Inbound note deleted"})}
