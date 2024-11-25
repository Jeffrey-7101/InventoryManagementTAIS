import json
import boto3
from decouple import config
from decimal import Decimal


AWS_REGION = "us-east-1"
DYNAMO_TABLE = config("DYNAMO_TABLE")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMO_TABLE)

def decimal_to_serializable(obj):
    """
    Convierte objetos de tipo Decimal a tipos JSON serializables
    (int o float), y procesa listas y diccionarios recursivamente.
    """
    if isinstance(obj, list):
        # Procesa listas recursivamente
        return [decimal_to_serializable(i) for i in obj]
    elif isinstance(obj, dict):
        # Procesa diccionarios recursivamente
        return {k: decimal_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        # Convierte Decimal a int o float
        return float(obj) if obj % 1 else int(obj)
    else:
        # Devuelve el objeto si no necesita conversión
        return obj

def create_product(event, context):
    body = json.loads(event["body"])
    product = {
        "ProductID": body["ProductID"],
        "Name": body["Name"],
        "Description": body["Description"],
        "Category": body["Category"],
        "Quantity": Decimal(0),
        "LastPrice":  Decimal(0.0)
    }
    table.put_item(Item=product)
    return {
        "statusCode": 201,
        "body": json.dumps({"message": "Product created successfully!"}),
    }


def get_all_products(event, context):
    query_params = event.get("queryStringParameters", {}) or {}
    search = query_params.get("search", "").lower()
    order_by = query_params.get("orderBy", "")
    category_filter = query_params.get("filter", "").lower()
    
    response = table.scan()
    items = response["Items"]

    if category_filter:
        items = [item for item in items if item.get("Category", "").lower() == category_filter]

    # Filtrar por el parámetro `search` (si existe)
    if search:
        items = [
            item
            for item in items
            if search in item.get("Name", "").lower()
            or search in item.get("Description", "").lower()
            or search in item.get("Category", "").lower()
        ]

    if order_by:
        reverse = order_by.startswith("-")  # Si comienza con "-", es orden descendente
        order_by_field = order_by.lstrip("-")  # Quita el prefijo "-" para obtener el campo
        items = sorted(
            items, key=lambda x: x.get(order_by_field, ""), reverse=reverse
        )

    items = decimal_to_serializable(items)

    return {
        "statusCode": 200,
        "body": json.dumps(items),
    }


def get_product(event, context):
    product_id = event["pathParameters"]["product_id"]
    response = table.get_item(Key={"ProductID": product_id})
    if "Item" not in response:
        return {
            "statusCode": 404,
            "body": json.dumps({"message": "Product not found"}),
        }
    return {
        "statusCode": 200,
        "body": json.dumps(response["Item"],default=decimal_to_serializable),
    }


def update_product(event, context):
    product_id = event["pathParameters"]["product_id"]
    body = json.loads(event["body"])
    update_expression = "SET "
    expression_attribute_values = {}
    expression_attribute_names = {}


    for key, value in body.items():
        if key == "Name":
            alias = "#name"
            expression_attribute_names[alias] = key
            update_expression += f"{alias} = :{key}, "
        else:
            update_expression += f"{key} = :{key}, "

        expression_attribute_values[f":{key}"] = (
            Decimal(value) if isinstance(value, (int, float)) else value
        )

    update_expression = update_expression.rstrip(", ")

    table.update_item(
        Key={"ProductID": product_id},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values,
        ExpressionAttributeNames=expression_attribute_names,
    )
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Product updated successfully!"}),
    }


def delete_product(event, context):
    product_id = event["pathParameters"]["product_id"]
    table.delete_item(Key={"ProductID": product_id})
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Product deleted successfully!"}),
    }
