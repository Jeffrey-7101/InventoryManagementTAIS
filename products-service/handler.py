import json
import boto3
from decouple import config

# Configuración DynamoDB
AWS_REGION = config("AWS_REGION")
DYNAMO_TABLE = config("DYNAMO_TABLE")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMO_TABLE)


def create_product(event, context):
    body = json.loads(event["body"])
    product = {
        "ProductID": body["ProductID"],
        "Name": body["Name"],
        "Description": body["Description"],
        "Category": body["Category"],
        "Quantity": 0,
        "LastPrice": 0.0
    }
    table.put_item(Item=product)
    return {
        "statusCode": 201,
        "body": json.dumps({"message": "Product created successfully!"}),
    }


def get_all_products(event, context):
    response = table.scan()
    return {
        "statusCode": 200,
        "body": json.dumps(response["Items"]),
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
        "body": json.dumps(response["Item"]),
    }


def update_product(event, context):
    product_id = event["pathParameters"]["product_id"]
    body = json.loads(event["body"])
    update_expression = "SET "
    expression_attribute_values = {}

    for key, value in body.items():
        update_expression += f"{key} = :{key}, "
        expression_attribute_values[f":{key}"] = value

    update_expression = update_expression.rstrip(", ")

    table.update_item(
        Key={"ProductID": product_id},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values,
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
