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
    
    required_fields = {
        "ProductID": str,
        "Name": str,
        "Category": str,
        "Quantity": int,
        "LastPrice": (int, float)
    }

    errors = []

    for field, field_type in required_fields.items():
        if field not in body:
            errors.append(f"Field '{field}' is required.")
        else:
            value = body[field]
            if not isinstance(value, field_type):
                errors.append(f"Field '{field}' must be of type {field_type.__name__}.")
            elif isinstance(value, str) and not value.strip():
                errors.append(f"Field '{field}' cannot be empty.")
            elif field == "Quantity" and value <= 0:
                errors.append("Field 'Quantity' must be greater than 0.")
            elif field == "LastPrice" and value <= 0:
                errors.append("Field 'LastPrice' must be greater than 0.")

    if errors:
        return {
            "statusCode": 400,
            "body": json.dumps({"errors": errors}),
        }

    response = table.get_item(Key={"ProductID": body["ProductID"]})
    if "Item" in response:
        return {
            "statusCode": 409,
            "body": json.dumps({"message": "ProductID already exists."}),
        }

    product = {
        "ProductID": body["ProductID"],
        "Name": body["Name"],
        "Description": body.get("Description", ""),  # Optional
        "Category": body["Category"],
        "Quantity": body["Quantity"],
        "LastPrice": body["LastPrice"]
    }
    table.put_item(Item=product)
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE"
        },
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
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE"
        },
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
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE"
        },
        "body": json.dumps(response["Item"],default=decimal_to_serializable),
    }

def update_product(event, context):
    product_id = event["pathParameters"]["product_id"]
    body = json.loads(event["body"])

    response = table.get_item(Key={"ProductID": product_id})
    if "Item" not in response:
        return {
            "statusCode": 404,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE"
            },
            "body": json.dumps({"message": "Product not found"}),
        }

    current_product = response["Item"]

    valid_fields = {
        "Name": str,
        "Description": str,
        "Category": str,
        "Quantity": int,
        "LastPrice": (int, float)
    }

    errors = []

    for key, value in body.items():
        if key not in valid_fields:
            errors.append(f"Field '{key}' is not a valid field to update.")
            continue  # Skip invalid fields

        expected_type = valid_fields[key]
        if not isinstance(value, expected_type):
            errors.append(f"Field '{key}' must be of type {expected_type.__name__}.")
        elif isinstance(value, str) and not value.strip():
            errors.append(f"Field '{key}' cannot be empty.")
        # elif key == "Quantity" and (current_product.get("Quantity", 0) + value) <= 0:
        #     errors.append("Resulting 'Quantity' must be greater than 0.")
        elif key == "Quantity":
            # Calculate the new quantity and check if it would result in a negative value
            new_quantity = current_product.get("Quantity", 0) + value
            if new_quantity < 0:
                errors.append(f"Resulting 'Quantity' cannot be less than 0. Current Quantity: {current_product.get('Quantity', 0)}, Adjustment: {value}")
        
        elif key == "LastPrice" and value <= 0:
            errors.append("Field 'LastPrice' must be greater than 0.")


    if errors:
        return {
            "statusCode": 400,
            "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE"
            },
            "body": json.dumps({"errors": errors}),
        }

    # Build update expression
    update_expression = "SET "
    expression_attribute_values = {}
    expression_attribute_names = {}

    for key, value in body.items():
        if key == "Name":
            alias = "#name"
            expression_attribute_names[alias] = key
            update_expression += f"{alias} = :{key}, "
            expression_attribute_values[f":{key}"] = value
        elif key == "Quantity":
            new_quantity = current_product.get("Quantity", 0) + value
            update_expression += f"{key} = :{key}, "
            expression_attribute_values[f":{key}"] = Decimal(new_quantity)
        else:
            update_expression += f"{key} = :{key}, "
            expression_attribute_values[f":{key}"] = Decimal(value) if isinstance(value, (int, float)) else value

    update_expression = update_expression.rstrip(", ")

    update_params = {
        "Key": {"ProductID": product_id},
        "UpdateExpression": update_expression,
        "ExpressionAttributeValues": expression_attribute_values,
    }
    if expression_attribute_names:
        update_params["ExpressionAttributeNames"] = expression_attribute_names

    table.update_item(**update_params)

    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE"
        },
        "body": json.dumps({"message": "Product updated successfully!"}),
    }

def delete_product(event, context):
    product_id = event["pathParameters"]["product_id"]
    table.delete_item(Key={"ProductID": product_id})
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE"
        },
        "body": json.dumps({"message": "Product deleted successfully!"}),
    }
