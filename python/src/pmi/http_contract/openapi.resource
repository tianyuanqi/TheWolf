{
  "openapi": "3.1.1",
  "info": {
    "title": "TheWolf market overview",
    "version": "3.0.0",
    "description": "Single SQLite storage and explicit fixed-version range reads. Old data is preserved offline; no legacy read fallback."
  },
  "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
  "paths": {
    "/api/health": {
      "get": {
        "operationId": "health",
        "responses": {
          "200": {
            "description": "公开存活探针，不读取金融数据。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Health"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              }
            }
          },
          "400": {
            "description": "Target boundary rejection; before business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              }
            }
          },
          "403": {
            "description": "Target boundary rejection; before business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              }
            }
          },
          "422": {
            "description": "Target boundary rejection; before business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              }
            }
          },
          "500": {
            "description": "Unhandled error; no diagnostic paths; client treats write result as unknown.",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              }
            }
          }
        },
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          }
        ],
        "x-wolf-response-context": "Required on successful response and business errors after context accepted; absent on boundary/pre-context or unhandled errors. Ready success also carries both. Consumer never accepts a body with mismatched/missing required context."
      },
      "options": {
        "operationId": "preflighthealth",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "600"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        }
      }
    },
    "/api/session/ready": {
      "get": {
        "operationId": "sessionReady",
        "responses": {
          "200": {
            "description": "当前实现响应",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/Ready"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "当前实现响应",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "Target boundary rejection; before business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "Target boundary rejection; before business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "Target boundary rejection; before business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          }
        ],
        "x-wolf-response-context": "Required on successful response and business errors after context accepted; absent on boundary/pre-context or unhandled errors. Ready success also carries both. Consumer never accepts a body with mismatched/missing required context."
      },
      "options": {
        "operationId": "preflightsessionReady",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "600"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        }
      }
    },
    "/api/index-series/session": {
      "get": {
        "operationId": "indexSeriesReady",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesReady"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "options": {
        "operationId": "preflightindexSeriesReady",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/index-series/catalog": {
      "get": {
        "operationId": "indexSeriesCatalog",
        "parameters": [
          {
            "name": "query",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "maxLength": 160
            }
          },
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesCatalog"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "options": {
        "operationId": "preflightindexSeriesCatalog",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/index-series/operations/{request_id}": {
      "get": {
        "operationId": "indexSeriesOperationResult",
        "parameters": [
          {
            "name": "instance_id",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/PublicInstanceId"
            }
          },
          {
            "name": "config_id",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/PublicDigest"
            }
          },
          {
            "name": "operation",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/IndexSeriesOperationKind"
            }
          },
          {
            "name": "index_id",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/IndexSeriesId"
            }
          },
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesOperationResult"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError409"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "parameters": [
        {
          "name": "request_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/RequestId"
          }
        }
      ],
      "options": {
        "operationId": "preflightindexSeriesOperationResult",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/index-series/{index_id}": {
      "get": {
        "operationId": "currentIndexSeries",
        "parameters": [
          {
            "name": "snapshot_id",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/ObjectId"
            }
          },
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesView"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "parameters": [
        {
          "name": "index_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/IndexSeriesId"
          }
        }
      ],
      "options": {
        "operationId": "preflightcurrentIndexSeries",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/index-series/{index_id}/snapshots/{snapshot_id}": {
      "get": {
        "operationId": "fixedIndexSeries",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesView"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "parameters": [
        {
          "name": "index_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/IndexSeriesId"
          }
        },
        {
          "name": "snapshot_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/ObjectId"
          }
        }
      ],
      "options": {
        "operationId": "preflightfixedIndexSeries",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/index-series/{index_id}/snapshots/{snapshot_id}/evidence/{object_id}": {
      "get": {
        "operationId": "indexSeriesEvidence",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesEvidenceView"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "parameters": [
        {
          "name": "index_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/IndexSeriesId"
          }
        },
        {
          "name": "snapshot_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/ObjectId"
          }
        },
        {
          "name": "object_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/ObjectId"
          }
        }
      ],
      "options": {
        "operationId": "preflightindexSeriesEvidence",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/index-series/{index_id}/range": {
      "get": {
        "operationId": "indexSeriesRange",
        "parameters": [
          {
            "name": "start",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/Day"
            }
          },
          {
            "name": "end",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/Day"
            }
          },
          {
            "name": "fields",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "pattern": "^(?:open|high|low|close)(?:,(?:open|high|low|close)){0,3}$(?![\\s\\S])",
              "description": "省略时为open,high,low,close；不允许重复字段，由业务校验拒绝。"
            }
          },
          {
            "name": "snapshot_id",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/ObjectId"
            }
          },
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesRange"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "parameters": [
        {
          "name": "index_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/IndexSeriesId"
          }
        }
      ],
      "options": {
        "operationId": "preflightindexSeriesRange",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/index-series/{index_id}/update": {
      "get": {
        "operationId": "indexSeriesStatus",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesUpdateStatus"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "post": {
        "operationId": "startIndexSeries",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "$ref": "#/components/parameters/RequestId"
          }
        ],
        "responses": {
          "202": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesAcceptedOperation"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "415": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError415"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "503": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError503"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/UpdateRequest"
              }
            }
          }
        },
        "description": "POST必须携带精确许可Origin；空JSON对象且最多4096字节。五元身份(instance/config/request/operation/index)重复只回放首次回执，跨身份复用409，不透明重试写入。"
      },
      "parameters": [
        {
          "name": "index_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/IndexSeriesId"
          }
        }
      ],
      "options": {
        "operationId": "preflightindexSeriesStatus",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET",
                "POST"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/index-series/{index_id}/snapshots/{snapshot_id}/calculations": {
      "get": {
        "operationId": "indexSeriesCalculations",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "name": "formula_version",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "index-price-calculations-v1"
              ]
            }
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IndexSeriesCalculations"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesCalculationError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesCalculationError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    },
                    {
                      "$ref": "#/components/schemas/IndexSeriesCalculationError"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "parameters": [
        {
          "name": "index_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/IndexSeriesId"
          }
        },
        {
          "name": "snapshot_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/ObjectId"
          }
        }
      ],
      "options": {
        "operationId": "preflightindexSeriesCalculations",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/market-activity/session": {
      "get": {
        "operationId": "marketActivityReady",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          }
        ],
        "responses": {
          "200": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MarketActivityReady"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-activity-config-v1：独立预期、固定实例及量额配置；旧v1/v2不能授权。"
      },
      "parameters": [],
      "options": {
        "operationId": "preflightmarketActivityReady",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/market-activity/operations/{request_id}": {
      "get": {
        "operationId": "marketActivityOperation",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "name": "series_id",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "sse:000001:price",
                "szse:399001:price",
                "szse:399006:price",
                "sse:000688:price",
                "cn-a-turnover",
                "cn-a-turnover-sse-szse"
              ]
            }
          }
        ],
        "responses": {
          "200": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MarketActivityOperation"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-activity-config-v1：独立预期、固定实例及量额配置；旧v1/v2不能授权。"
      },
      "parameters": [
        {
          "name": "request_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/RequestId"
          }
        }
      ],
      "options": {
        "operationId": "preflightmarketActivityOperation",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/market-activity/{series_id}": {
      "get": {
        "operationId": "currentMarketActivity",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "name": "price_snapshot_id",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/ObjectId"
            }
          },
          {
            "name": "anchor_date",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MarketActivityCurrent"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-activity-config-v1：独立预期、固定实例及量额配置；旧v1/v2不能授权。"
      },
      "parameters": [
        {
          "name": "series_id",
          "in": "path",
          "required": true,
          "schema": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          }
        }
      ],
      "options": {
        "operationId": "preflightcurrentMarketActivity",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/market-activity/{series_id}/snapshots/{activity_id}": {
      "get": {
        "operationId": "fixedMarketActivity",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MarketActivitySnapshot"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-activity-config-v1：独立预期、固定实例及量额配置；旧v1/v2不能授权。"
      },
      "parameters": [
        {
          "name": "series_id",
          "in": "path",
          "required": true,
          "schema": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          }
        },
        {
          "name": "activity_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/ObjectId"
          }
        }
      ],
      "options": {
        "operationId": "preflightfixedMarketActivity",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/market-activity/{series_id}/snapshots/{activity_id}/calculations": {
      "get": {
        "operationId": "marketActivityCalculations",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "name": "formula_version",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "market-activity-calculations-v1",
                "market-activity-calculations-sse-szse-v1"
              ]
            }
          }
        ],
        "responses": {
          "200": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MarketActivityCalculations"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-activity-config-v1：独立预期、固定实例及量额配置；旧v1/v2不能授权。"
      },
      "parameters": [
        {
          "name": "series_id",
          "in": "path",
          "required": true,
          "schema": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          }
        },
        {
          "name": "activity_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/ObjectId"
          }
        }
      ],
      "options": {
        "operationId": "preflightmarketActivityCalculations",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/market-activity/{series_id}/snapshots/{activity_id}/evidence/{object_id}": {
      "get": {
        "operationId": "marketActivityEvidence",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MarketActivityEvidence"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-activity-config-v1：独立预期、固定实例及量额配置；旧v1/v2不能授权。"
      },
      "parameters": [
        {
          "name": "series_id",
          "in": "path",
          "required": true,
          "schema": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          }
        },
        {
          "name": "activity_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/ObjectId"
          }
        },
        {
          "name": "object_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/ObjectId"
          }
        }
      ],
      "options": {
        "operationId": "preflightmarketActivityEvidence",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/market-activity/{series_id}/update": {
      "post": {
        "operationId": "startMarketActivity",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "$ref": "#/components/parameters/RequestId"
          }
        ],
        "responses": {
          "200": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MarketActivityOperation"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "415": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError415"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-activity-config-v1：独立预期、固定实例及量额配置；旧v1/v2不能授权。",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/MarketActivityUpdateBody"
              }
            }
          }
        }
      },
      "parameters": [
        {
          "name": "series_id",
          "in": "path",
          "required": true,
          "schema": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          }
        }
      ],
      "options": {
        "operationId": "preflightstartMarketActivity",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "POST"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/overview-update/status": {
      "get": {
        "operationId": "overviewUpdateStatus",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OverviewUpdateStatus"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError422"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。"
      },
      "options": {
        "operationId": "preflightOverviewUpdateStatus",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/etf-flow/session": {
      "parameters": [],
      "options": {
        "operationId": "preflightetfFlowReady",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      },
      "get": {
        "operationId": "etfFlowReady",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          }
        ],
        "responses": {
          "200": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/EtfReady"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-etf-flow-config-v1：独立可信配置、当前连接身份及原持久请求身份分别核对。"
      }
    },
    "/api/etf-flow/current": {
      "parameters": [],
      "options": {
        "operationId": "preflightcurrentEtfFlow",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      },
      "get": {
        "operationId": "currentEtfFlow",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/EtfCurrent"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-etf-flow-config-v1：独立可信配置、当前连接身份及原持久请求身份分别核对。"
      }
    },
    "/api/etf-flow/snapshots/{snapshot_id}": {
      "parameters": [
        {
          "name": "snapshot_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/PublicDigest"
          }
        }
      ],
      "options": {
        "operationId": "preflightetfFlowView",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      },
      "get": {
        "operationId": "etfFlowView",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "name": "mode",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "original",
                "current"
              ]
            }
          },
          {
            "name": "period",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "20",
                "60",
                "120",
                "260"
              ]
            }
          },
          {
            "name": "end",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
            }
          },
          {
            "name": "group",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/PublicDigest"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/EtfView"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-etf-flow-config-v1：独立可信配置、当前连接身份及原持久请求身份分别核对。"
      }
    },
    "/api/etf-flow/snapshots/{snapshot_id}/evidence/{object_id}": {
      "parameters": [
        {
          "name": "snapshot_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/PublicDigest"
          }
        },
        {
          "name": "object_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/PublicDigest"
          }
        }
      ],
      "options": {
        "operationId": "preflightetfFlowEvidence",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      },
      "get": {
        "operationId": "etfFlowEvidence",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/EtfEvidence"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-etf-flow-config-v1：独立可信配置、当前连接身份及原持久请求身份分别核对。"
      }
    },
    "/api/etf-flow/update": {
      "parameters": [],
      "options": {
        "operationId": "preflightstartEtfFlow",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "POST"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      },
      "post": {
        "operationId": "startEtfFlow",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "$ref": "#/components/parameters/RequestId"
          }
        ],
        "responses": {
          "200": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/EtfOperation"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "202": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/EtfOperation"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "415": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError415"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-etf-flow-config-v1：独立可信配置、当前连接身份及原持久请求身份分别核对。",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/EtfUpdateBody"
              }
            }
          }
        }
      }
    },
    "/api/etf-flow/operations/{request_id}": {
      "parameters": [
        {
          "name": "request_id",
          "in": "path",
          "required": true,
          "schema": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          }
        }
      ],
      "options": {
        "operationId": "preflightetfFlowOperation",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      },
      "get": {
        "operationId": "etfFlowOperation",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/EtfOperation"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "ETF固定身份响应；缺数据与未记录不会伪装为零或正常。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/EtfError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-etf-flow-config-v1：独立可信配置、当前连接身份及原持久请求身份分别核对。"
      }
    },
    "/api/index-series/{index_id}/view": {
      "get": {
        "operationId": "indexSeriesView",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "name": "snapshot_id",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/ObjectId"
            }
          },
          {
            "name": "observation_id",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/ObjectId"
            }
          },
          {
            "name": "formula_version",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "const": "index-price-calculations-v1"
            }
          },
          {
            "name": "detail",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "overview",
                "range"
              ]
            }
          },
          {
            "name": "start",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/Day"
            }
          },
          {
            "name": "end",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/Day"
            }
          },
          {
            "name": "frequency",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "enum": [
                "daily",
                "weekly",
                "monthly"
              ]
            }
          },
          {
            "name": "ma",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "pattern": "^(none|(?:5|10|20|30|60|120|180|250)(?:,(?:5|10|20|30|60|120|180|250))*)$"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/StoredPriceView"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。",
        "description": "按固定发布/观察返回概况或所请求范围，普通读取仅查询SQLite。"
      },
      "parameters": [
        {
          "name": "index_id",
          "in": "path",
          "required": true,
          "schema": {
            "$ref": "#/components/schemas/IndexSeriesId"
          }
        }
      ],
      "options": {
        "operationId": "preflightindexSeriesView",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/market-activity/{series_id}/view": {
      "get": {
        "operationId": "marketActivityView",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          },
          {
            "name": "activity_id",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/ObjectId"
            }
          },
          {
            "name": "observation_id",
            "in": "query",
            "required": true,
            "schema": {
              "$ref": "#/components/schemas/ObjectId"
            }
          },
          {
            "name": "price_snapshot_id",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/ObjectId"
            }
          },
          {
            "name": "anchor_date",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/Day"
            }
          },
          {
            "name": "formula_version",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "market-activity-calculations-v1",
                "market-activity-calculations-sse-szse-v1"
              ]
            }
          },
          {
            "name": "detail",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "overview",
                "range"
              ]
            }
          },
          {
            "name": "start",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/Day"
            }
          },
          {
            "name": "end",
            "in": "query",
            "required": false,
            "schema": {
              "$ref": "#/components/schemas/Day"
            }
          },
          {
            "name": "frequency",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "enum": [
                "daily",
                "weekly",
                "monthly"
              ]
            }
          },
          {
            "name": "ma",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "pattern": "^(none|(?:5|10|20|30|60|120|180|250)(?:,(?:5|10|20|30|60|120|180|250))*)$"
            }
          },
          {
            "name": "field",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "enum": [
                "volume",
                "amount"
              ]
            }
          }
        ],
        "responses": {
          "200": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/StoredActivityView"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError400"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError403"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "B量额身份校验后的响应；来源缺口不代表有效数据。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/MarketActivityError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "wolf-activity-config-v1：独立预期、固定实例及量额配置；旧v1/v2不能授权。",
        "description": "固定价格/anchor与活动版本绑定，按需读取单字段单周期；普通读取不重验原件。"
      },
      "parameters": [
        {
          "name": "series_id",
          "in": "path",
          "required": true,
          "schema": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          }
        }
      ],
      "options": {
        "operationId": "preflightmarketActivityView",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/storage/versions": {
      "get": {
        "operationId": "marketVersions",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MarketVersions"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。",
        "description": "按固定发布/观察返回概况或所请求范围，普通读取仅查询SQLite。"
      },
      "options": {
        "operationId": "preflightmarketVersions",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    },
    "/api/storage/status": {
      "get": {
        "operationId": "storageStatus",
        "parameters": [
          {
            "$ref": "#/components/parameters/ClientMarker"
          },
          {
            "$ref": "#/components/parameters/ExpectedInstance"
          },
          {
            "$ref": "#/components/parameters/ExpectedConfig"
          }
        ],
        "responses": {
          "200": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/StorageStatus"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "400": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "403": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "404": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError404"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "409": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError409"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "422": {
            "description": "新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。",
            "content": {
              "application/json": {
                "schema": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/IndexSeriesError"
                    },
                    {
                      "$ref": "#/components/schemas/BoundaryError422"
                    }
                  ]
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          },
          "500": {
            "description": "未处理异常不泄露内部资料；写入结果不能据此推定回滚。",
            "content": {
              "text/plain": {
                "schema": {
                  "$ref": "#/components/schemas/InternalError"
                }
              }
            },
            "headers": {
              "Cache-Control": {
                "$ref": "#/components/headers/NoStore"
              },
              "X-Wolf-Instance": {
                "$ref": "#/components/headers/ResponseInstance"
              },
              "X-Wolf-Config": {
                "$ref": "#/components/headers/ResponseConfig"
              }
            }
          }
        },
        "x-wolf-response-context": "新特性身份格式wolf-index-config-v2；X-Wolf-Expected-Config与X-Wolf-Config使用新index_config_id。成功与已接受上下文的业务错误须有实际同instance及新config响应头；边界/未处理错误不作归属证明。session仅公开元数据，不作为调用者可信预期。",
        "description": "按固定发布/观察返回概况或所请求范围，普通读取仅查询SQLite。"
      },
      "options": {
        "operationId": "preflightstorageStatus",
        "parameters": [
          {
            "name": "Origin",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          },
          {
            "name": "Access-Control-Request-Method",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "GET"
              ]
            }
          },
          {
            "name": "Access-Control-Request-Headers",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string",
              "minLength": 1
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Valid metadata-only preflight. No body or business I/O.",
            "headers": {
              "Access-Control-Allow-Origin": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Methods": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Allow-Headers": {
                "schema": {
                  "type": "string"
                }
              },
              "Access-Control-Max-Age": {
                "schema": {
                  "type": "string",
                  "const": "0"
                }
              },
              "Vary": {
                "schema": {
                  "type": "string",
                  "const": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                }
              }
            }
          },
          "400": {
            "description": "Malformed preflight.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError400"
                }
              }
            }
          },
          "403": {
            "description": "Host, Origin or metadata denied.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError403"
                }
              }
            }
          },
          "404": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError404"
                }
              }
            }
          },
          "405": {
            "description": "Preflight route/method fallback; no business I/O.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BoundaryError405"
                }
              }
            }
          }
        },
        "x-wolf-response-context": "只校验新特性预检元数据，不读取业务、不核对实例/配置值；max-age为0。"
      }
    }
  },
  "components": {
    "schemas": {
      "Health": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "const": "ok"
          },
          "service": {
            "type": "string",
            "const": "thewolf-local-service"
          },
          "storage": {
            "type": "string",
            "const": "sqlite"
          }
        },
        "required": [
          "status",
          "service",
          "storage"
        ],
        "additionalProperties": false
      },
      "ObjectId": {
        "type": "string",
        "pattern": "^[0-9a-f]{64}$(?![\\s\\S])",
        "description": "内容或观察SHA-256；不是job ID或Git提交。"
      },
      "Day": {
        "type": "string",
        "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$(?![\\s\\S])"
      },
      "Point": {
        "type": "string",
        "pattern": "^[0-9]+\\.[0-9]{2}$(?![\\s\\S])",
        "description": "原十进制点位字符串；单位与精度引用既有指数数据约定，不作浮点转换。"
      },
      "Percent": {
        "type": "string",
        "pattern": "^-?[0-9]+\\.[0-9]{2}$(?![\\s\\S])"
      },
      "EvidenceRef": {
        "type": "object",
        "properties": {
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "locator": {
            "type": "string"
          }
        },
        "required": [
          "object_id",
          "locator"
        ],
        "additionalProperties": false
      },
      "Bar": {
        "type": "object",
        "properties": {
          "trade_date": {
            "$ref": "#/components/schemas/Day"
          },
          "open": {
            "$ref": "#/components/schemas/Point"
          },
          "high": {
            "$ref": "#/components/schemas/Point"
          },
          "low": {
            "$ref": "#/components/schemas/Point"
          },
          "close": {
            "$ref": "#/components/schemas/Point"
          },
          "evidence_refs": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EvidenceRef"
            },
            "minItems": 2,
            "maxItems": 2
          }
        },
        "required": [
          "trade_date",
          "open",
          "high",
          "low",
          "close",
          "evidence_refs"
        ],
        "additionalProperties": false
      },
      "SourceRow": {
        "type": "object",
        "properties": {
          "trade_date": {
            "$ref": "#/components/schemas/Day"
          },
          "open": {
            "$ref": "#/components/schemas/Point"
          },
          "high": {
            "$ref": "#/components/schemas/Point"
          },
          "low": {
            "$ref": "#/components/schemas/Point"
          },
          "close": {
            "$ref": "#/components/schemas/Point"
          },
          "locator": {
            "type": "string"
          },
          "raw_values": {
            "type": "object",
            "additionalProperties": {
              "type": "string"
            },
            "properties": {
              "open": {
                "type": "string"
              },
              "high": {
                "type": "string"
              },
              "low": {
                "type": "string"
              },
              "close": {
                "type": "string"
              }
            },
            "required": [
              "open",
              "high",
              "low",
              "close"
            ]
          }
        },
        "required": [
          "trade_date",
          "open",
          "high",
          "low",
          "close",
          "locator",
          "raw_values"
        ],
        "additionalProperties": false
      },
      "Source": {
        "type": "string",
        "enum": [
          "eastmoney",
          "tencent",
          "csindex"
        ]
      },
      "Evidence": {
        "type": "object",
        "properties": {
          "source": {
            "$ref": "#/components/schemas/Source"
          },
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "url": {
            "type": "string"
          },
          "rows": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/SourceRow"
            },
            "minItems": 260,
            "maxItems": 260
          }
        },
        "required": [
          "source",
          "object_id",
          "url",
          "rows"
        ],
        "additionalProperties": false
      },
      "TencentSourceContract": {
        "type": "object",
        "properties": {
          "date_selection": {
            "type": "string",
            "const": "exclude earlier rows; reject later, duplicate or unordered dates; retain original array index"
          },
          "identity_basis": {
            "type": "string",
            "const": "PLAN-P01 official factsheet; H00300/N00300 excluded"
          },
          "normalization": {
            "type": "string",
            "const": "decimal-two-places-v1"
          },
          "publication_time": {
            "type": "string",
            "const": "unknown"
          },
          "request_qfq_semantics": {
            "type": "string",
            "const": "SDK compatibility parameter; price index day only"
          },
          "sources": {
            "type": "object",
            "properties": {
              "csindex": {
                "type": "string"
              },
              "tencent": {
                "type": "string"
              }
            },
            "required": [
              "csindex",
              "tencent"
            ],
            "additionalProperties": false
          },
          "tencent_branch": {
            "type": "string",
            "const": "day"
          },
          "unused_fields": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "version": {
            "type": "string",
            "const": "csi300-tencent-exact-ohlc-v2"
          }
        },
        "required": [
          "date_selection",
          "identity_basis",
          "normalization",
          "publication_time",
          "request_qfq_semantics",
          "sources",
          "tencent_branch",
          "unused_fields",
          "version"
        ],
        "additionalProperties": false
      },
      "SourceContract": {
        "oneOf": [
          {
            "$ref": "#/components/schemas/TencentSourceContract"
          }
        ]
      },
      "Summary": {
        "type": "object",
        "properties": {
          "close": {
            "$ref": "#/components/schemas/Point"
          },
          "trade_date": {
            "$ref": "#/components/schemas/Day"
          },
          "daily_change_pct": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/Percent"
              },
              {
                "type": "null"
              }
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "enum": [
                  "first_row_without_previous_close"
                ]
              },
              {
                "type": "null"
              }
            ]
          },
          "formula_version": {
            "type": "string",
            "const": "adjacent-expected-close-pct-half-up-v1"
          },
          "input_refs": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "close": {
                  "$ref": "#/components/schemas/Point"
                },
                "trade_date": {
                  "$ref": "#/components/schemas/Day"
                },
                "evidence_refs": {
                  "type": "array",
                  "items": {
                    "$ref": "#/components/schemas/EvidenceRef"
                  },
                  "minItems": 2,
                  "maxItems": 2
                }
              },
              "required": [
                "close",
                "trade_date",
                "evidence_refs"
              ],
              "additionalProperties": false
            },
            "minItems": 1,
            "maxItems": 2
          }
        },
        "required": [
          "close",
          "trade_date",
          "daily_change_pct",
          "reason",
          "formula_version",
          "input_refs"
        ],
        "additionalProperties": false
      },
      "RetrievalSource": {
        "type": "object",
        "properties": {
          "source": {
            "$ref": "#/components/schemas/Source"
          },
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "url": {
            "type": "string"
          },
          "started_at": {
            "type": "string"
          },
          "completed_at": {
            "type": "string"
          },
          "published_at": {
            "type": "null"
          }
        },
        "required": [
          "source",
          "object_id",
          "url",
          "started_at",
          "completed_at",
          "published_at"
        ],
        "additionalProperties": false
      },
      "Retrieval": {
        "type": "object",
        "properties": {
          "observed_at": {
            "type": "string"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/RetrievalSource"
            },
            "minItems": 2,
            "maxItems": 2
          }
        },
        "required": [
          "observed_at",
          "snapshot_id",
          "sources"
        ],
        "additionalProperties": false
      },
      "CompletionBasis": {
        "type": "object",
        "properties": {
          "coverage": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "limits": {
            "type": "string"
          },
          "rule": {
            "type": "string"
          },
          "sources": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "sha256": {
                  "type": "string"
                },
                "url": {
                  "type": "string"
                }
              },
              "required": [
                "sha256",
                "url"
              ],
              "additionalProperties": false
            }
          },
          "version": {
            "type": "string"
          }
        },
        "required": [
          "coverage",
          "limits",
          "rule",
          "sources",
          "version"
        ],
        "additionalProperties": false
      },
      "Instrument": {
        "type": "object",
        "properties": {
          "code": {
            "type": "string",
            "const": "000300"
          },
          "frequency": {
            "type": "string",
            "const": "daily"
          },
          "id": {
            "type": "string",
            "const": "csi:000300:price"
          },
          "name": {
            "type": "string",
            "const": "沪深300"
          },
          "provider": {
            "type": "string",
            "const": "中证"
          },
          "return_type": {
            "type": "string",
            "const": "price"
          }
        },
        "required": [
          "code",
          "frequency",
          "id",
          "name",
          "provider",
          "return_type"
        ],
        "additionalProperties": false
      },
      "Window": {
        "type": "object",
        "properties": {
          "start": {
            "$ref": "#/components/schemas/Day"
          },
          "end": {
            "$ref": "#/components/schemas/Day"
          },
          "expected_count": {
            "type": "integer",
            "const": 260
          },
          "actual_count": {
            "type": "integer",
            "const": 260
          }
        },
        "required": [
          "start",
          "end",
          "expected_count",
          "actual_count"
        ],
        "additionalProperties": false
      },
      "IndexView": {
        "type": "object",
        "properties": {
          "bars": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Bar"
            },
            "minItems": 260,
            "maxItems": 260
          },
          "calendar_dates": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Day"
            },
            "minItems": 260,
            "maxItems": 260
          },
          "completion_basis": {
            "$ref": "#/components/schemas/CompletionBasis"
          },
          "evidence": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Evidence"
            },
            "minItems": 2,
            "maxItems": 2
          },
          "instrument": {
            "$ref": "#/components/schemas/Instrument"
          },
          "pit_grade": {
            "type": "string",
            "const": "latest_only"
          },
          "schema_version": {
            "type": "string",
            "const": "csi300-price-snapshot-v1"
          },
          "source_contract": {
            "$ref": "#/components/schemas/SourceContract"
          },
          "summary": {
            "$ref": "#/components/schemas/Summary"
          },
          "timezone": {
            "type": "string",
            "const": "Asia/Shanghai"
          },
          "unit": {
            "type": "string",
            "const": "点"
          },
          "window": {
            "$ref": "#/components/schemas/Window"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "retrieval": {
            "$ref": "#/components/schemas/Retrieval"
          }
        },
        "required": [
          "bars",
          "calendar_dates",
          "completion_basis",
          "evidence",
          "instrument",
          "pit_grade",
          "schema_version",
          "source_contract",
          "summary",
          "timezone",
          "unit",
          "window",
          "snapshot_id",
          "observation_id",
          "retrieval"
        ],
        "additionalProperties": false
      },
      "UpdateRequest": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      },
      "Ready": {
        "type": "object",
        "properties": {
          "status": {
            "const": "ready",
            "type": "string"
          },
          "service_id": {
            "const": "thewolf-local-service",
            "type": "string"
          },
          "service_version": {
            "type": "string",
            "minLength": 1
          },
          "contract_version": {
            "const": "3.0.0",
            "type": "string"
          },
          "contract_sha256": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          },
          "data_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "identity_format": {
            "const": "wolf-config-v2",
            "type": "string"
          }
        },
        "required": [
          "status",
          "service_id",
          "service_version",
          "contract_version",
          "contract_sha256",
          "instance_id",
          "data_scope_id",
          "config_id",
          "identity_format"
        ],
        "additionalProperties": false
      },
      "InternalError": {
        "type": "string",
        "const": "Internal Server Error"
      },
      "IndexEvidence": {
        "type": "object",
        "properties": {
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "source": {
            "$ref": "#/components/schemas/Source"
          },
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "url": {
            "type": "string"
          },
          "rows": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/SourceRow"
            },
            "minItems": 260,
            "maxItems": 260
          },
          "retrieval": {
            "$ref": "#/components/schemas/RetrievalSource"
          },
          "verification": {
            "type": "string"
          },
          "unused_fields": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "text_preview": {
            "type": "string"
          },
          "preview_truncated": {
            "type": "boolean"
          }
        },
        "required": [
          "snapshot_id",
          "observation_id",
          "source",
          "object_id",
          "url",
          "rows",
          "retrieval",
          "verification",
          "unused_fields",
          "text_preview",
          "preview_truncated"
        ],
        "additionalProperties": false
      },
      "PublicInstanceId": {
        "type": "string",
        "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
      },
      "PublicDigest": {
        "type": "string",
        "pattern": "^[0-9a-f]{64}$"
      },
      "RequestId": {
        "type": "string",
        "minLength": 1,
        "maxLength": 128,
        "pattern": "^[A-Za-z0-9._:-]+$"
      },
      "BoundaryError400": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "invalid_headers",
                  "connection_context_required",
                  "connection_context_invalid",
                  "invalid_preflight"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "BoundaryError403": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "bad_host",
                  "bad_origin",
                  "bad_fetch_metadata",
                  "client_marker_required",
                  "update_disabled",
                  "index_update_disabled"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "BoundaryError404": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "route_not_found"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "BoundaryError405": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "method_not_allowed"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "BoundaryError409": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "connection_context_mismatch",
                  "request_id_conflict"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "BoundaryError415": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "unsupported_media_type"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "BoundaryError422": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "invalid_request"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "BoundaryError503": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "operation_capacity_exceeded"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "IndexSeriesId": {
        "type": "string",
        "enum": [
          "csi:000300:price",
          "sse:000001:price",
          "csi:000852:price",
          "szse:399001:price",
          "szse:399006:price",
          "sse:000688:price"
        ]
      },
      "IndexSeriesSource": {
        "type": "string",
        "enum": [
          "csindex",
          "cnindex",
          "eastmoney"
        ]
      },
      "IndexSeriesSourcePolicy": {
        "type": "string",
        "enum": [
          "index-csindex-eastmoney-exact-v1",
          "index-cnindex-eastmoney-rounding-aware-v1"
        ]
      },
      "IndexSeriesPoint": {
        "type": "string",
        "pattern": "^(?:0|[1-9][0-9]*)\\.[0-9]{2}(?:[0-9]{2})?$(?![\\s\\S])",
        "description": "官方原值以十进制字符串保留两位或四位；深圳四位值仅核验时HALF_UP到两位，不改写存储或计算输入。"
      },
      "IndexSeriesRawPoint": {
        "type": "string",
        "pattern": "^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$(?![\\s\\S])",
        "maxLength": 40
      },
      "IndexSeriesRawPriceFields": {
        "type": "object",
        "properties": {
          "open": {
            "$ref": "#/components/schemas/IndexSeriesRawPoint"
          },
          "high": {
            "$ref": "#/components/schemas/IndexSeriesRawPoint"
          },
          "low": {
            "$ref": "#/components/schemas/IndexSeriesRawPoint"
          },
          "close": {
            "$ref": "#/components/schemas/IndexSeriesRawPoint"
          }
        },
        "required": [
          "open",
          "high",
          "low",
          "close"
        ],
        "additionalProperties": false
      },
      "IndexSeriesComparisonFields": {
        "type": "object",
        "properties": {
          "open": {
            "$ref": "#/components/schemas/Point"
          },
          "high": {
            "$ref": "#/components/schemas/Point"
          },
          "low": {
            "$ref": "#/components/schemas/Point"
          },
          "close": {
            "$ref": "#/components/schemas/Point"
          }
        },
        "required": [
          "open",
          "high",
          "low",
          "close"
        ],
        "additionalProperties": false
      },
      "IndexSeriesField": {
        "type": "string",
        "enum": [
          "open",
          "high",
          "low",
          "close"
        ]
      },
      "IndexSeriesNetworkPolicy": {
        "type": "object",
        "properties": {
          "max_attempts": {
            "type": "integer"
          },
          "max_bytes": {
            "type": "integer"
          },
          "max_response_bytes": {
            "type": "integer",
            "const": 1048576
          },
          "min_host_interval_seconds": {
            "type": "integer",
            "const": 5
          },
          "deadline_seconds": {
            "type": "integer",
            "const": 45
          }
        },
        "required": [
          "max_attempts",
          "max_bytes",
          "max_response_bytes",
          "min_host_interval_seconds",
          "deadline_seconds"
        ],
        "additionalProperties": false
      },
      "IndexSeriesPolicy": {
        "type": "object",
        "properties": {
          "feature_version": {
            "type": "string",
            "const": "index-series-v2"
          },
          "catalog_version": {
            "type": "string",
            "const": "index-catalog-v1"
          },
          "calendar_version": {
            "type": "string",
            "const": "cn-indices-sse-szse-2023-2026-v1"
          },
          "window_years": {
            "type": "integer",
            "const": 3
          },
          "source_policy_versions": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesSourcePolicy"
            },
            "minItems": 2,
            "maxItems": 2
          },
          "network": {
            "$ref": "#/components/schemas/IndexSeriesNetworkPolicy"
          },
          "periodic": {
            "$ref": "#/components/schemas/OverviewPeriodicPolicy"
          }
        },
        "required": [
          "feature_version",
          "catalog_version",
          "calendar_version",
          "window_years",
          "source_policy_versions",
          "network"
        ],
        "additionalProperties": false
      },
      "IndexSeriesReady": {
        "type": "object",
        "properties": {
          "status": {
            "const": "ready",
            "type": "string"
          },
          "service_id": {
            "const": "thewolf-local-service",
            "type": "string"
          },
          "service_version": {
            "type": "string",
            "minLength": 1
          },
          "contract_version": {
            "const": "3.0.0",
            "type": "string"
          },
          "contract_sha256": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          },
          "data_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "identity_format": {
            "type": "string",
            "const": "wolf-index-config-v2"
          },
          "feature_version": {
            "type": "string",
            "const": "index-series-v2"
          },
          "write_indices": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesId"
            },
            "maxItems": 6
          },
          "startup_indices": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesId"
            },
            "maxItems": 6
          },
          "policy": {
            "$ref": "#/components/schemas/IndexSeriesPolicy"
          }
        },
        "required": [
          "status",
          "service_id",
          "service_version",
          "contract_version",
          "contract_sha256",
          "instance_id",
          "data_scope_id",
          "config_id",
          "identity_format",
          "feature_version",
          "write_indices",
          "startup_indices",
          "policy"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCatalogEntry": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "code": {
            "type": "string",
            "pattern": "^[0-9]{6}$(?![\\s\\S])"
          },
          "name": {
            "type": "string",
            "minLength": 1
          },
          "full_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "provider": {
            "type": "string",
            "enum": [
              "csindex",
              "cnindex"
            ]
          },
          "return_type": {
            "type": "string",
            "const": "price"
          },
          "frequency": {
            "type": "string",
            "const": "daily"
          },
          "aliases": {
            "type": "array",
            "items": {
              "type": "string",
              "minLength": 1
            }
          },
          "storage_decimals": {
            "type": "integer",
            "enum": [
              2,
              4
            ]
          },
          "source_policy_version": {
            "$ref": "#/components/schemas/IndexSeriesSourcePolicy"
          },
          "capabilities": {
            "type": "object",
            "properties": {
              "ohlc": {
                "type": "string",
                "const": "available"
              },
              "amount": {
                "type": "string",
                "const": "unavailable"
              },
              "valuation": {
                "type": "string",
                "const": "unavailable"
              }
            },
            "required": [
              "ohlc",
              "amount",
              "valuation"
            ],
            "additionalProperties": false
          },
          "limitations": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "writable": {
            "type": "boolean"
          }
        },
        "required": [
          "index_id",
          "code",
          "name",
          "full_name",
          "provider",
          "return_type",
          "frequency",
          "aliases",
          "storage_decimals",
          "source_policy_version",
          "capabilities",
          "limitations",
          "writable"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCatalog": {
        "type": "object",
        "properties": {
          "catalog_version": {
            "type": "string",
            "const": "index-catalog-v1"
          },
          "query": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 160
              },
              {
                "type": "null"
              }
            ]
          },
          "resolved_index_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/IndexSeriesId"
              },
              {
                "type": "null"
              }
            ]
          },
          "indices": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesCatalogEntry"
            },
            "maxItems": 6
          }
        },
        "required": [
          "catalog_version",
          "query",
          "resolved_index_id",
          "indices"
        ],
        "additionalProperties": false
      },
      "IndexSeriesInstrument": {
        "type": "object",
        "properties": {
          "id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "code": {
            "type": "string",
            "pattern": "^[0-9]{6}$(?![\\s\\S])"
          },
          "name": {
            "type": "string",
            "minLength": 1
          },
          "full_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "provider": {
            "type": "string",
            "enum": [
              "csindex",
              "cnindex"
            ]
          },
          "return_type": {
            "type": "string",
            "const": "price"
          },
          "frequency": {
            "type": "string",
            "const": "daily"
          }
        },
        "required": [
          "id",
          "code",
          "name",
          "full_name",
          "provider",
          "return_type",
          "frequency"
        ],
        "additionalProperties": false
      },
      "IndexSeriesWindow": {
        "type": "object",
        "properties": {
          "version": {
            "type": "string",
            "const": "three-natural-years-before-shanghai-day-v1"
          },
          "anchor_date": {
            "$ref": "#/components/schemas/Day"
          },
          "natural_start": {
            "$ref": "#/components/schemas/Day"
          },
          "start": {
            "$ref": "#/components/schemas/Day"
          },
          "end": {
            "$ref": "#/components/schemas/Day"
          },
          "expected_count": {
            "type": "integer"
          },
          "actual_count": {
            "type": "integer"
          }
        },
        "required": [
          "version",
          "anchor_date",
          "natural_start",
          "start",
          "end",
          "expected_count",
          "actual_count"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCalendarSource": {
        "type": "object",
        "properties": {
          "year": {
            "type": "integer",
            "enum": [
              2023,
              2024,
              2025,
              2026
            ]
          },
          "exchange": {
            "type": "string",
            "enum": [
              "sse",
              "szse"
            ]
          },
          "url": {
            "type": "string"
          },
          "evidence_kind": {
            "type": "string",
            "enum": [
              "web_tool_text",
              "http_original"
            ]
          },
          "evidence_sha256": {
            "$ref": "#/components/schemas/ObjectId"
          }
        },
        "required": [
          "year",
          "exchange",
          "url",
          "evidence_kind",
          "evidence_sha256"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCompletionBasis": {
        "type": "object",
        "properties": {
          "rule": {
            "type": "string",
            "const": "exchange_weekdays_excluding_announced_full_day_closures_before_shanghai_today"
          },
          "timezone": {
            "type": "string",
            "const": "Asia/Shanghai"
          },
          "exclude_anchor_day": {
            "type": "boolean",
            "const": true
          },
          "supported_years": {
            "type": "array",
            "items": {
              "type": "integer",
              "enum": [
                2023,
                2024,
                2025,
                2026
              ]
            },
            "minItems": 4,
            "maxItems": 4
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesCalendarSource"
            },
            "minItems": 8,
            "maxItems": 8
          },
          "limitations": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        },
        "required": [
          "rule",
          "timezone",
          "exclude_anchor_day",
          "supported_years",
          "sources",
          "limitations"
        ],
        "additionalProperties": false
      },
      "IndexSeriesVerification": {
        "type": "object",
        "properties": {
          "mode": {
            "type": "string",
            "enum": [
              "exact",
              "rounding_aware"
            ]
          },
          "primary_source": {
            "type": "string",
            "enum": [
              "csindex",
              "cnindex"
            ]
          },
          "verification_source": {
            "type": "string",
            "const": "eastmoney"
          },
          "comparison_decimals": {
            "type": "integer",
            "const": 2
          },
          "comparison_rounding": {
            "anyOf": [
              {
                "type": "string",
                "const": "ROUND_HALF_UP"
              },
              {
                "type": "null"
              }
            ]
          },
          "result": {
            "type": "string",
            "const": "matched"
          },
          "limitations": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        },
        "required": [
          "mode",
          "primary_source",
          "verification_source",
          "comparison_decimals",
          "comparison_rounding",
          "result",
          "limitations"
        ],
        "additionalProperties": false
      },
      "IndexSeriesEvidenceRef": {
        "type": "object",
        "properties": {
          "source": {
            "$ref": "#/components/schemas/IndexSeriesSource"
          },
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "locator": {
            "type": "string",
            "minLength": 1
          }
        },
        "required": [
          "source",
          "object_id",
          "locator"
        ],
        "additionalProperties": false
      },
      "IndexSeriesBar": {
        "type": "object",
        "properties": {
          "trade_date": {
            "$ref": "#/components/schemas/Day"
          },
          "open": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "high": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "low": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "close": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "evidence_refs": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesEvidenceRef"
            },
            "minItems": 2,
            "maxItems": 2
          }
        },
        "required": [
          "trade_date",
          "open",
          "high",
          "low",
          "close",
          "evidence_refs"
        ],
        "additionalProperties": false
      },
      "IndexSeriesSourceRow": {
        "type": "object",
        "properties": {
          "trade_date": {
            "$ref": "#/components/schemas/Day"
          },
          "open": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "high": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "low": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "close": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "locator": {
            "type": "string",
            "minLength": 1
          },
          "raw_values": {
            "$ref": "#/components/schemas/IndexSeriesRawPriceFields"
          },
          "comparison_values": {
            "$ref": "#/components/schemas/IndexSeriesComparisonFields"
          }
        },
        "required": [
          "trade_date",
          "open",
          "high",
          "low",
          "close",
          "locator",
          "raw_values",
          "comparison_values"
        ],
        "additionalProperties": false
      },
      "IndexSeriesEvidence": {
        "type": "object",
        "properties": {
          "source": {
            "$ref": "#/components/schemas/IndexSeriesSource"
          },
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "url": {
            "type": "string"
          },
          "rows": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesSourceRow"
            },
            "minItems": 1
          }
        },
        "required": [
          "source",
          "object_id",
          "url",
          "rows"
        ],
        "additionalProperties": false
      },
      "IndexSeriesSummaryInput": {
        "type": "object",
        "properties": {
          "trade_date": {
            "$ref": "#/components/schemas/Day"
          },
          "close": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "evidence_refs": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesEvidenceRef"
            },
            "minItems": 2,
            "maxItems": 2
          }
        },
        "required": [
          "trade_date",
          "close",
          "evidence_refs"
        ],
        "additionalProperties": false
      },
      "IndexSeriesSummary": {
        "type": "object",
        "properties": {
          "trade_date": {
            "$ref": "#/components/schemas/Day"
          },
          "close": {
            "$ref": "#/components/schemas/IndexSeriesPoint"
          },
          "daily_change_pct": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/Percent"
              },
              {
                "type": "null"
              }
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "const": "first_row_without_previous_close"
              },
              {
                "type": "null"
              }
            ]
          },
          "formula_version": {
            "type": "string",
            "const": "adjacent-expected-close-pct-half-up-v1"
          },
          "input_refs": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesSummaryInput"
            },
            "minItems": 1,
            "maxItems": 2
          }
        },
        "required": [
          "trade_date",
          "close",
          "daily_change_pct",
          "reason",
          "formula_version",
          "input_refs"
        ],
        "additionalProperties": false
      },
      "IndexSeriesRetrievalSource": {
        "type": "object",
        "properties": {
          "source": {
            "$ref": "#/components/schemas/IndexSeriesSource"
          },
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "url": {
            "type": "string"
          },
          "started_at": {
            "type": "string"
          },
          "completed_at": {
            "type": "string"
          },
          "published_at": {
            "type": "null"
          }
        },
        "required": [
          "source",
          "object_id",
          "url",
          "started_at",
          "completed_at",
          "published_at"
        ],
        "additionalProperties": false
      },
      "IndexSeriesRetrieval": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesRetrievalSource"
            },
            "minItems": 2,
            "maxItems": 2
          },
          "observed_at": {
            "type": "string"
          }
        },
        "required": [
          "index_id",
          "snapshot_id",
          "sources",
          "observed_at"
        ],
        "additionalProperties": false
      },
      "IndexSeriesSnapshot": {
        "type": "object",
        "properties": {
          "schema_version": {
            "type": "string",
            "const": "index-series-price-snapshot-v2"
          },
          "catalog_version": {
            "type": "string",
            "const": "index-catalog-v1"
          },
          "instrument": {
            "$ref": "#/components/schemas/IndexSeriesInstrument"
          },
          "source_policy_version": {
            "$ref": "#/components/schemas/IndexSeriesSourcePolicy"
          },
          "calendar_version": {
            "type": "string",
            "const": "cn-indices-sse-szse-2023-2026-v1"
          },
          "unit": {
            "type": "string",
            "const": "点"
          },
          "timezone": {
            "type": "string",
            "const": "Asia/Shanghai"
          },
          "pit_grade": {
            "type": "string",
            "const": "latest_only"
          },
          "storage_decimals": {
            "type": "integer",
            "enum": [
              2,
              4
            ]
          },
          "window": {
            "$ref": "#/components/schemas/IndexSeriesWindow"
          },
          "calendar_dates": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Day"
            },
            "minItems": 1
          },
          "completion_basis": {
            "$ref": "#/components/schemas/IndexSeriesCompletionBasis"
          },
          "verification": {
            "$ref": "#/components/schemas/IndexSeriesVerification"
          },
          "bars": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesBar"
            },
            "minItems": 1
          },
          "summary": {
            "$ref": "#/components/schemas/IndexSeriesSummary"
          },
          "evidence": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesEvidence"
            },
            "minItems": 2,
            "maxItems": 2
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "retrieval": {
            "$ref": "#/components/schemas/IndexSeriesRetrieval"
          }
        },
        "required": [
          "schema_version",
          "catalog_version",
          "instrument",
          "source_policy_version",
          "calendar_version",
          "unit",
          "timezone",
          "pit_grade",
          "storage_decimals",
          "window",
          "calendar_dates",
          "completion_basis",
          "verification",
          "bars",
          "summary",
          "evidence",
          "snapshot_id",
          "observation_id",
          "retrieval"
        ],
        "additionalProperties": false
      },
      "IndexSeriesView": {
        "oneOf": [
          {
            "type": "object",
            "properties": {
              "index_id": {
                "$ref": "#/components/schemas/IndexSeriesId"
              },
              "format": {
                "type": "string",
                "const": "v2"
              },
              "snapshot": {
                "$ref": "#/components/schemas/IndexSeriesSnapshot"
              }
            },
            "required": [
              "index_id",
              "format",
              "snapshot"
            ],
            "additionalProperties": false
          },
          {
            "type": "object",
            "properties": {
              "index_id": {
                "type": "string",
                "const": "csi:000300:price"
              },
              "format": {
                "type": "string",
                "const": "legacy_v1"
              },
              "snapshot": {
                "$ref": "#/components/schemas/IndexView"
              }
            },
            "required": [
              "index_id",
              "format",
              "snapshot"
            ],
            "additionalProperties": false
          }
        ]
      },
      "IndexSeriesEvidenceDetail": {
        "type": "object",
        "properties": {
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "source": {
            "$ref": "#/components/schemas/IndexSeriesSource"
          },
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "url": {
            "type": "string"
          },
          "rows": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesSourceRow"
            },
            "minItems": 1
          },
          "retrieval": {
            "$ref": "#/components/schemas/IndexSeriesRetrievalSource"
          },
          "verification": {
            "$ref": "#/components/schemas/IndexSeriesVerification"
          },
          "text_preview": {
            "type": "string"
          },
          "preview_truncated": {
            "type": "boolean"
          }
        },
        "required": [
          "snapshot_id",
          "observation_id",
          "source",
          "object_id",
          "url",
          "rows",
          "retrieval",
          "verification",
          "text_preview",
          "preview_truncated"
        ],
        "additionalProperties": false
      },
      "IndexSeriesEvidenceView": {
        "oneOf": [
          {
            "type": "object",
            "properties": {
              "index_id": {
                "$ref": "#/components/schemas/IndexSeriesId"
              },
              "format": {
                "type": "string",
                "const": "v2"
              },
              "evidence": {
                "$ref": "#/components/schemas/IndexSeriesEvidenceDetail"
              }
            },
            "required": [
              "index_id",
              "format",
              "evidence"
            ],
            "additionalProperties": false
          },
          {
            "type": "object",
            "properties": {
              "index_id": {
                "type": "string",
                "const": "csi:000300:price"
              },
              "format": {
                "type": "string",
                "const": "legacy_v1"
              },
              "evidence": {
                "$ref": "#/components/schemas/IndexEvidence"
              }
            },
            "required": [
              "index_id",
              "format",
              "evidence"
            ],
            "additionalProperties": false
          }
        ]
      },
      "IndexSeriesRangeRow": {
        "type": "object",
        "properties": {
          "trade_date": {
            "$ref": "#/components/schemas/Day"
          },
          "values": {
            "type": "object",
            "properties": {
              "open": {
                "$ref": "#/components/schemas/IndexSeriesPoint"
              },
              "high": {
                "$ref": "#/components/schemas/IndexSeriesPoint"
              },
              "low": {
                "$ref": "#/components/schemas/IndexSeriesPoint"
              },
              "close": {
                "$ref": "#/components/schemas/IndexSeriesPoint"
              }
            },
            "required": [],
            "additionalProperties": false
          }
        },
        "required": [
          "trade_date",
          "values"
        ],
        "additionalProperties": false
      },
      "IndexSeriesRange": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "format": {
            "type": "string",
            "enum": [
              "v2",
              "legacy_v1"
            ]
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "start": {
            "$ref": "#/components/schemas/Day"
          },
          "end": {
            "$ref": "#/components/schemas/Day"
          },
          "fields": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesField"
            },
            "minItems": 1,
            "maxItems": 4
          },
          "unit": {
            "type": "string",
            "const": "点"
          },
          "pit_grade": {
            "type": "string",
            "const": "latest_only"
          },
          "storage_decimals": {
            "type": "integer",
            "enum": [
              2,
              4
            ]
          },
          "coverage": {
            "type": "object",
            "properties": {
              "start": {
                "$ref": "#/components/schemas/Day"
              },
              "end": {
                "$ref": "#/components/schemas/Day"
              }
            },
            "required": [
              "start",
              "end"
            ],
            "additionalProperties": false
          },
          "rows": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesRangeRow"
            }
          }
        },
        "required": [
          "index_id",
          "format",
          "snapshot_id",
          "start",
          "end",
          "fields",
          "unit",
          "pit_grade",
          "storage_decimals",
          "coverage",
          "rows"
        ],
        "additionalProperties": false
      },
      "IndexSeriesDifference": {
        "type": "object",
        "properties": {
          "date": {
            "$ref": "#/components/schemas/Day"
          },
          "field": {
            "$ref": "#/components/schemas/IndexSeriesField"
          },
          "official_raw": {
            "$ref": "#/components/schemas/IndexSeriesRawPoint"
          },
          "comparison_value": {
            "$ref": "#/components/schemas/Point"
          },
          "eastmoney_raw": {
            "$ref": "#/components/schemas/IndexSeriesRawPoint"
          }
        },
        "required": [
          "date",
          "field",
          "official_raw",
          "comparison_value",
          "eastmoney_raw"
        ],
        "additionalProperties": false
      },
      "IndexSeriesUpdateStatus": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "job_id": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1
              },
              {
                "type": "null"
              }
            ]
          },
          "trigger": {
            "anyOf": [
              {
                "type": "string",
                "enum": [
                  "manual",
                  "startup"
                ]
              },
              {
                "type": "null"
              }
            ]
          },
          "stage": {
            "type": "string",
            "enum": [
              "idle",
              "preparing",
              "fetching_csindex",
              "fetching_cnindex",
              "fetching_eastmoney",
              "validating",
              "publishing",
              "completed",
              "failed",
              "interrupted"
            ]
          },
          "result": {
            "anyOf": [
              {
                "type": "string",
                "enum": [
                  "business_changed",
                  "evidence_changed",
                  "unchanged",
                  "source_not_ready",
                  "failed",
                  "interrupted"
                ]
              },
              {
                "type": "null"
              }
            ]
          },
          "started_at": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "finished_at": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "last_success_at": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "message": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "target_start": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/Day"
              },
              {
                "type": "null"
              }
            ]
          },
          "target_end": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/Day"
              },
              {
                "type": "null"
              }
            ]
          },
          "previous_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "observation_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "added_dates": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Day"
            }
          },
          "revised_dates": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Day"
            }
          },
          "differences": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesDifference"
            }
          },
          "enabled": {
            "type": "boolean"
          }
        },
        "required": [
          "index_id",
          "job_id",
          "trigger",
          "stage",
          "result",
          "started_at",
          "finished_at",
          "last_success_at",
          "message",
          "target_start",
          "target_end",
          "previous_snapshot_id",
          "snapshot_id",
          "observation_id",
          "added_dates",
          "revised_dates",
          "differences",
          "enabled"
        ],
        "additionalProperties": false
      },
      "IndexSeriesError": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "index_series_empty",
                  "index_series_snapshot_not_found",
                  "index_series_unavailable",
                  "index_series_invalid",
                  "index_series_evidence_not_found",
                  "index_range_invalid",
                  "coverage_insufficient",
                  "range_parameters_invalid",
                  "range_coverage_insufficient",
                  "storage_publication_not_found",
                  "storage_observation_not_member",
                  "storage_activity_binding_invalid",
                  "storage_quarantined",
                  "storage_integrity_check_due",
                  "storage_maintenance_failed"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "IndexSeriesRecordedRejection": {
        "type": "object",
        "properties": {
          "status": {
            "type": "integer",
            "const": 409
          },
          "body": {
            "$ref": "#/components/schemas/IndexSeriesError"
          }
        },
        "required": [
          "status",
          "body"
        ],
        "additionalProperties": false
      },
      "IndexSeriesOperationKind": {
        "type": "string",
        "const": "index.series.update"
      },
      "IndexSeriesAcceptedOperation": {
        "type": "object",
        "properties": {
          "instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "request_id": {
            "$ref": "#/components/schemas/RequestId"
          },
          "operation": {
            "$ref": "#/components/schemas/IndexSeriesOperationKind"
          },
          "state": {
            "type": "string",
            "enum": [
              "accepted",
              "running"
            ]
          },
          "job_id": {
            "type": "string",
            "minLength": 1
          },
          "reused_job": {
            "type": "boolean"
          },
          "business_status": {
            "$ref": "#/components/schemas/IndexSeriesUpdateStatus"
          },
          "rejection": {
            "type": "null"
          },
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          }
        },
        "required": [
          "instance_id",
          "config_id",
          "request_id",
          "operation",
          "state",
          "job_id",
          "reused_job",
          "business_status",
          "rejection",
          "index_id"
        ],
        "additionalProperties": false
      },
      "IndexSeriesOperationResult": {
        "type": "object",
        "properties": {
          "instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "request_id": {
            "$ref": "#/components/schemas/RequestId"
          },
          "operation": {
            "$ref": "#/components/schemas/IndexSeriesOperationKind"
          },
          "state": {
            "type": "string",
            "enum": [
              "accepted",
              "running",
              "completed",
              "failed",
              "interrupted",
              "rejected",
              "unknown"
            ]
          },
          "job_id": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1
              },
              {
                "type": "null"
              }
            ]
          },
          "reused_job": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ]
          },
          "business_status": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/IndexSeriesUpdateStatus"
              },
              {
                "type": "null"
              }
            ]
          },
          "rejection": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/IndexSeriesRecordedRejection"
              },
              {
                "type": "null"
              }
            ]
          },
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          }
        },
        "required": [
          "instance_id",
          "config_id",
          "request_id",
          "operation",
          "state",
          "job_id",
          "reused_job",
          "business_status",
          "rejection",
          "index_id"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCalculationInput": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "start": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/Day"
              },
              {
                "type": "null"
              }
            ]
          },
          "end": {
            "$ref": "#/components/schemas/Day"
          }
        },
        "required": [
          "index_id",
          "snapshot_id",
          "start",
          "end"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCalculationParameters": {
        "type": "object",
        "properties": {
          "frequency": {
            "type": "string",
            "enum": [
              "daily",
              "weekly",
              "monthly"
            ]
          },
          "period": {
            "type": "string",
            "enum": [
              "1",
              "5",
              "10",
              "20",
              "30",
              "60",
              "120",
              "180",
              "250",
              "1y"
            ]
          }
        },
        "required": [
          "frequency",
          "period"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCalculationScalar": {
        "type": "object",
        "properties": {
          "value": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?[0-9]+\\.[0-9]{2}([0-9]{2})?$",
                "maxLength": 64
              },
              {
                "type": "null"
              }
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "enum": [
                  "insufficient_samples",
                  "missing_previous_close",
                  "missing_year_baseline"
                ]
              },
              {
                "type": "null"
              }
            ]
          },
          "unit": {
            "type": "string",
            "enum": [
              "%",
              "点"
            ]
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "adjacent-expected-close-pct-half-up-v1",
              "period-close-pct-half-up-v1",
              "trading-window-close-pct-v1",
              "natural-year-close-pct-v1",
              "close-sma-half-up-4-v1"
            ]
          },
          "parameters": {
            "$ref": "#/components/schemas/IndexSeriesCalculationParameters"
          },
          "input_ref": {
            "$ref": "#/components/schemas/IndexSeriesCalculationInput"
          }
        },
        "required": [
          "value",
          "reason",
          "unit",
          "formula_version",
          "parameters",
          "input_ref"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCalculationBar": {
        "type": "object",
        "properties": {
          "period_start": {
            "$ref": "#/components/schemas/Day"
          },
          "period_end": {
            "$ref": "#/components/schemas/Day"
          },
          "start": {
            "$ref": "#/components/schemas/Day"
          },
          "end": {
            "$ref": "#/components/schemas/Day"
          },
          "open": {
            "type": "string",
            "pattern": "^[0-9]+\\.[0-9]{2}([0-9]{2})?$",
            "maxLength": 45
          },
          "high": {
            "type": "string",
            "pattern": "^[0-9]+\\.[0-9]{2}([0-9]{2})?$",
            "maxLength": 45
          },
          "low": {
            "type": "string",
            "pattern": "^[0-9]+\\.[0-9]{2}([0-9]{2})?$",
            "maxLength": 45
          },
          "close": {
            "type": "string",
            "pattern": "^[0-9]+\\.[0-9]{2}([0-9]{2})?$",
            "maxLength": 45
          },
          "sample_count": {
            "type": "integer"
          },
          "complete": {
            "type": "boolean"
          },
          "incomplete_reasons": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "window_start_truncated",
                "period_in_progress",
                "calendar_unknown"
              ]
            },
            "maxItems": 3
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "raw-daily-price-v1",
              "calendar-ohlc-v1"
            ]
          },
          "input_ref": {
            "$ref": "#/components/schemas/IndexSeriesCalculationInput"
          },
          "change_pct": {
            "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
          },
          "ma": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
            },
            "maxItems": 8
          }
        },
        "required": [
          "period_start",
          "period_end",
          "start",
          "end",
          "open",
          "high",
          "low",
          "close",
          "sample_count",
          "complete",
          "incomplete_reasons",
          "formula_version",
          "input_ref",
          "change_pct",
          "ma"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCalculationAvailability": {
        "type": "object",
        "properties": {
          "period": {
            "type": "integer",
            "enum": [
              5,
              10,
              20,
              30,
              60,
              120,
              180,
              250
            ]
          },
          "available": {
            "type": "boolean"
          },
          "sample_count": {
            "type": "integer"
          },
          "required_count": {
            "type": "integer",
            "enum": [
              5,
              10,
              20,
              30,
              60,
              120,
              180,
              250
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "enum": [
                  "insufficient_samples"
                ]
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "period",
          "available",
          "sample_count",
          "required_count",
          "reason"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCalculationSeries": {
        "type": "object",
        "properties": {
          "frequency": {
            "type": "string",
            "enum": [
              "daily",
              "weekly",
              "monthly"
            ]
          },
          "ma_availability": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesCalculationAvailability"
            },
            "maxItems": 8
          },
          "rows": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesCalculationBar"
            },
            "maxItems": 1100
          }
        },
        "required": [
          "frequency",
          "ma_availability",
          "rows"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCalculations": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "formula_version": {
            "type": "string",
            "const": "index-price-calculations-v1"
          },
          "calendar_version": {
            "type": "string",
            "const": "cn-indices-sse-szse-2023-2026-v1"
          },
          "anchor_date": {
            "$ref": "#/components/schemas/Day"
          },
          "pit_grade": {
            "type": "string",
            "const": "latest_only"
          },
          "unit": {
            "type": "string",
            "const": "点"
          },
          "daily": {
            "$ref": "#/components/schemas/IndexSeriesCalculationSeries"
          },
          "weekly": {
            "$ref": "#/components/schemas/IndexSeriesCalculationSeries"
          },
          "monthly": {
            "$ref": "#/components/schemas/IndexSeriesCalculationSeries"
          },
          "performance": {
            "type": "object",
            "properties": {
              "day_5": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              },
              "day_20": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              },
              "day_60": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              },
              "year_1": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              }
            },
            "required": [
              "day_5",
              "day_20",
              "day_60",
              "year_1"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "index_id",
          "snapshot_id",
          "formula_version",
          "calendar_version",
          "anchor_date",
          "pit_grade",
          "unit",
          "daily",
          "weekly",
          "monthly",
          "performance"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCalculationError": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "index_series_empty",
                  "index_series_snapshot_not_found",
                  "index_series_unavailable",
                  "index_series_invalid",
                  "index_series_evidence_not_found",
                  "index_range_invalid",
                  "coverage_insufficient",
                  "calculation_parameters_invalid",
                  "range_parameters_invalid",
                  "range_coverage_insufficient",
                  "storage_publication_not_found",
                  "storage_observation_not_member",
                  "storage_activity_binding_invalid",
                  "storage_quarantined",
                  "storage_integrity_check_due",
                  "storage_maintenance_failed"
                ]
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "MarketActivityPolicy": {
        "type": "object",
        "properties": {
          "version": {
            "type": "string"
          },
          "binding_version": {
            "type": "string"
          },
          "window_years": {
            "type": "integer"
          },
          "sources": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "series": {
                  "type": "string"
                },
                "source": {
                  "type": "string"
                },
                "amount_unit": {
                  "type": "string"
                },
                "amount_quantum": {
                  "type": "string"
                },
                "volume_unit": {
                  "anyOf": [
                    {
                      "type": "string"
                    },
                    {
                      "type": "null"
                    }
                  ]
                },
                "scope": {
                  "type": "string"
                },
                "gaps": {
                  "type": "array",
                  "items": {
                    "type": "string"
                  }
                },
                "admitted": {
                  "type": "boolean"
                },
                "version": {
                  "type": "string"
                }
              },
              "required": [
                "series",
                "source",
                "amount_unit",
                "amount_quantum",
                "volume_unit",
                "scope",
                "gaps",
                "admitted",
                "version"
              ],
              "additionalProperties": false
            }
          },
          "network": {
            "type": "object",
            "properties": {
              "max_attempts": {
                "type": "integer"
              },
              "max_bytes": {
                "type": "integer"
              },
              "max_response_bytes": {
                "type": "integer"
              },
              "timeout_seconds": {
                "type": "integer"
              },
              "deadline_seconds": {
                "type": "integer"
              },
              "minimum_interval_seconds": {
                "type": "integer"
              },
              "redirects": {
                "type": "boolean"
              },
              "retries": {
                "type": "integer"
              },
              "max_operation_requests": {
                "type": "integer"
              },
              "budget_cycle": {
                "type": "string"
              },
              "ledger_version": {
                "type": "string"
              },
              "ledger_scope": {
                "anyOf": [
                  {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  {
                    "type": "null"
                  }
                ]
              }
            },
            "required": [
              "max_attempts",
              "max_bytes",
              "max_response_bytes",
              "timeout_seconds",
              "deadline_seconds",
              "minimum_interval_seconds",
              "redirects",
              "retries",
              "max_operation_requests",
              "budget_cycle",
              "ledger_version",
              "ledger_scope"
            ],
            "additionalProperties": false
          },
          "parser": {
            "type": "object",
            "properties": {
              "version": {
                "type": "string"
              },
              "max_rows": {
                "type": "integer"
              },
              "xlsx_members": {
                "type": "integer"
              },
              "xlsx_expanded_bytes": {
                "type": "integer"
              },
              "xlsx_cells": {
                "type": "integer"
              }
            },
            "required": [
              "version",
              "max_rows",
              "xlsx_members",
              "xlsx_expanded_bytes",
              "xlsx_cells"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "version",
          "binding_version",
          "window_years",
          "sources",
          "network",
          "parser"
        ],
        "additionalProperties": false
      },
      "MarketActivityFact": {
        "type": "object",
        "properties": {
          "value": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "unit": {
            "type": "string",
            "enum": [
              "股",
              "元"
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "raw_value": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "raw_unit": {
            "type": "string"
          },
          "source_quantum": {
            "type": "string"
          },
          "object_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "locator": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "value",
          "unit",
          "reason",
          "raw_value",
          "raw_unit",
          "source_quantum",
          "object_id",
          "locator"
        ],
        "additionalProperties": false
      },
      "MarketActivitySnapshot": {
        "oneOf": [
          {
            "$ref": "#/components/schemas/MarketActivityIndexSnapshot"
          },
          {
            "$ref": "#/components/schemas/MarketActivityMarketSnapshot"
          },
          {
            "$ref": "#/components/schemas/MarketActivityTwoMarketSnapshot"
          }
        ]
      },
      "MarketActivityCurrent": {
        "type": "object",
        "properties": {
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "price_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "anchor_date": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "coverage_start": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "coverage_end": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "missing_dates": {
            "type": "array",
            "items": {
              "type": "string",
              "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
            }
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          }
        },
        "required": [
          "series_id",
          "activity_id",
          "price_snapshot_id",
          "anchor_date",
          "coverage_start",
          "coverage_end",
          "missing_dates",
          "observation_id"
        ],
        "additionalProperties": false
      },
      "MarketActivityScalar": {
        "type": "object",
        "properties": {
          "value": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "unit": {
            "type": "string"
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "market-activity-calculations-v1",
              "market-activity-calculations-sse-szse-v1"
            ]
          },
          "parameters": {
            "type": "object",
            "properties": {
              "field": {
                "type": "string"
              },
              "frequency": {
                "type": "string"
              },
              "operation": {
                "type": "string"
              },
              "period": {
                "type": "string"
              }
            },
            "required": [
              "field",
              "frequency",
              "operation",
              "period"
            ],
            "additionalProperties": false
          },
          "input_ref": {
            "type": "object",
            "properties": {
              "series_id": {
                "type": "string",
                "enum": [
                  "sse:000001:price",
                  "szse:399001:price",
                  "szse:399006:price",
                  "sse:000688:price",
                  "cn-a-turnover",
                  "cn-a-turnover-sse-szse"
                ]
              },
              "activity_id": {
                "$ref": "#/components/schemas/ObjectId"
              },
              "price_snapshot_id": {
                "anyOf": [
                  {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "start": {
                "anyOf": [
                  {
                    "type": "string",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "end": {
                "type": "string",
                "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
              }
            },
            "required": [
              "series_id",
              "activity_id",
              "price_snapshot_id",
              "start",
              "end"
            ],
            "additionalProperties": false
          },
          "complete": {
            "type": "boolean"
          },
          "incomplete_reasons": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        },
        "required": [
          "value",
          "reason",
          "unit",
          "formula_version",
          "parameters",
          "input_ref",
          "complete",
          "incomplete_reasons"
        ],
        "additionalProperties": false
      },
      "MarketActivityCalculations": {
        "type": "object",
        "properties": {
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "price_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "market-activity-calculations-v1",
              "market-activity-calculations-sse-szse-v1"
            ]
          },
          "pit_grade": {
            "const": "latest_only",
            "type": "string"
          },
          "series": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "frequency": {
                  "type": "string",
                  "enum": [
                    "daily",
                    "weekly",
                    "monthly"
                  ]
                },
                "field": {
                  "type": "string",
                  "enum": [
                    "volume",
                    "amount"
                  ]
                },
                "rows": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "start": {
                        "type": "string",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                      },
                      "end": {
                        "type": "string",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                      },
                      "period_start": {
                        "type": "string",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                      },
                      "period_end": {
                        "type": "string",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                      },
                      "sample_count": {
                        "type": "integer"
                      },
                      "total": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "change_pct": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "ma": {
                        "type": "array",
                        "items": {
                          "$ref": "#/components/schemas/MarketActivityScalar"
                        }
                      }
                    },
                    "required": [
                      "start",
                      "end",
                      "period_start",
                      "period_end",
                      "sample_count",
                      "total",
                      "change_pct",
                      "ma"
                    ],
                    "additionalProperties": false
                  }
                },
                "ma_availability": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "period": {
                        "type": "integer"
                      },
                      "available": {
                        "type": "boolean"
                      },
                      "sample_count": {
                        "type": "integer"
                      },
                      "required_count": {
                        "type": "integer"
                      },
                      "reason": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      }
                    },
                    "required": [
                      "period",
                      "available",
                      "sample_count",
                      "required_count",
                      "reason"
                    ],
                    "additionalProperties": false
                  }
                }
              },
              "required": [
                "frequency",
                "field",
                "rows",
                "ma_availability"
              ],
              "additionalProperties": false
            }
          },
          "comparisons": {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "day_5": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  },
                  "day_20": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  },
                  "day_60": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  },
                  "year_1": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  }
                },
                "required": [
                  "day_5",
                  "day_20",
                  "day_60",
                  "year_1"
                ],
                "additionalProperties": false
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "series_id",
          "activity_id",
          "price_snapshot_id",
          "formula_version",
          "pit_grade",
          "series",
          "comparisons"
        ],
        "additionalProperties": false
      },
      "MarketActivityEvidence": {
        "type": "object",
        "properties": {
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "source": {
            "type": "string"
          },
          "url": {
            "type": "string"
          },
          "published_at": {
            "type": "null"
          },
          "content_base64": {
            "type": "string"
          },
          "byte_length": {
            "type": "integer"
          },
          "price_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "observations": {
            "type": "array",
            "minItems": 1,
            "items": {
              "$ref": "#/components/schemas/MarketActivityObservation"
            }
          }
        },
        "required": [
          "series_id",
          "activity_id",
          "object_id",
          "source",
          "url",
          "published_at",
          "content_base64",
          "byte_length",
          "price_snapshot_id",
          "observations"
        ],
        "additionalProperties": false
      },
      "MarketActivityOperation": {
        "type": "object",
        "properties": {
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          },
          "request_id": {
            "$ref": "#/components/schemas/RequestId"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          },
          "target": {
            "type": "string"
          },
          "signature": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "state": {
            "type": "string",
            "enum": [
              "preparing",
              "completed",
              "failed",
              "interrupted"
            ]
          },
          "activity_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "recovered_from_instance": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PublicInstanceId"
              },
              {
                "type": "null"
              }
            ]
          },
          "observation_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "series_id",
          "request_id",
          "config_id",
          "instance_id",
          "target",
          "signature",
          "state",
          "activity_id",
          "reason",
          "recovered_from_instance",
          "observation_id"
        ],
        "additionalProperties": false
      },
      "MarketActivityUpdateBody": {
        "oneOf": [
          {
            "type": "object",
            "properties": {
              "price_snapshot_id": {
                "$ref": "#/components/schemas/ObjectId"
              },
              "expected_activity_id": {
                "anyOf": [
                  {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  {
                    "type": "null"
                  }
                ]
              }
            },
            "required": [
              "price_snapshot_id",
              "expected_activity_id"
            ],
            "additionalProperties": false
          },
          {
            "type": "object",
            "properties": {
              "anchor_date": {
                "type": "string",
                "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
              },
              "expected_activity_id": {
                "anyOf": [
                  {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  {
                    "type": "null"
                  }
                ]
              }
            },
            "required": [
              "anchor_date",
              "expected_activity_id"
            ],
            "additionalProperties": false
          }
        ]
      },
      "MarketActivityError": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string"
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "MarketActivityReady": {
        "type": "object",
        "properties": {
          "service_id": {
            "const": "thewolf-local-service",
            "type": "string"
          },
          "service_version": {
            "type": "string",
            "minLength": 1
          },
          "contract_version": {
            "const": "3.0.0",
            "type": "string"
          },
          "contract_sha256": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "data_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "identity_format": {
            "const": "wolf-activity-config-v1",
            "type": "string"
          },
          "feature_version": {
            "const": "market-activity-v1",
            "type": "string"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "price_index_config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "activity_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "series": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "sse:000001:price",
                "szse:399001:price",
                "szse:399006:price",
                "sse:000688:price",
                "cn-a-turnover",
                "cn-a-turnover-sse-szse"
              ]
            }
          },
          "write_series": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "sse:000001:price",
                "szse:399001:price",
                "szse:399006:price",
                "sse:000688:price",
                "cn-a-turnover",
                "cn-a-turnover-sse-szse"
              ]
            }
          },
          "startup_series": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "sse:000001:price",
                "szse:399001:price",
                "szse:399006:price",
                "sse:000688:price",
                "cn-a-turnover",
                "cn-a-turnover-sse-szse"
              ]
            },
            "maxItems": 6
          },
          "blocked_series": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "series_id": {
                  "type": "string",
                  "enum": [
                    "sse:000001:price",
                    "szse:399001:price",
                    "szse:399006:price",
                    "sse:000688:price",
                    "cn-a-turnover",
                    "cn-a-turnover-sse-szse"
                  ]
                },
                "evidence_id": {
                  "$ref": "#/components/schemas/ObjectId"
                },
                "reason": {
                  "const": "source_withdrawn",
                  "type": "string"
                }
              },
              "required": [
                "series_id",
                "evidence_id",
                "reason"
              ],
              "additionalProperties": false
            }
          },
          "policy": {
            "$ref": "#/components/schemas/MarketActivityPolicy"
          },
          "instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          },
          "status": {
            "const": "ready",
            "type": "string"
          },
          "market_anchor_date": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "market_anchors": {
            "$ref": "#/components/schemas/MarketActivityAnchors"
          }
        },
        "required": [
          "service_id",
          "service_version",
          "contract_version",
          "contract_sha256",
          "data_scope_id",
          "identity_format",
          "feature_version",
          "config_id",
          "price_index_config_id",
          "activity_scope_id",
          "series",
          "write_series",
          "startup_series",
          "blocked_series",
          "policy",
          "instance_id",
          "status",
          "market_anchor_date"
        ],
        "additionalProperties": false
      },
      "MarketActivityIndexSnapshot": {
        "type": "object",
        "properties": {
          "schema_version": {
            "const": "activity-facts-v1",
            "type": "string"
          },
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover"
            ]
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "price_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "anchor_date": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "window": {
            "$ref": "#/components/schemas/IndexSeriesWindow"
          },
          "calendar_version": {
            "type": "string"
          },
          "calendar_dates": {
            "type": "array",
            "items": {
              "type": "string",
              "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
            }
          },
          "source_policy_version": {
            "type": "string"
          },
          "parser_version": {
            "type": "string"
          },
          "pit_grade": {
            "const": "latest_only",
            "type": "string"
          },
          "currency": {
            "const": "CNY",
            "type": "string"
          },
          "source_scope": {
            "type": "string"
          },
          "source_revision_relation": {
            "const": "unknown",
            "type": "string"
          },
          "source_revision_id": {
            "type": "null"
          },
          "binding": {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "version": {
                    "type": "string"
                  },
                  "price_object_id": {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  "activity_object_id": {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  "relation": {
                    "type": "string",
                    "enum": [
                      "same_source_object",
                      "different_source_objects"
                    ]
                  },
                  "comparison": {
                    "const": "exact_available_values_match",
                    "type": "string"
                  },
                  "rows": {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "trade_date": {
                          "type": "string",
                          "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                        },
                        "price_locator": {
                          "type": "string"
                        },
                        "activity_locator": {
                          "type": "string"
                        }
                      },
                      "required": [
                        "trade_date",
                        "price_locator",
                        "activity_locator"
                      ],
                      "additionalProperties": false
                    }
                  }
                },
                "required": [
                  "version",
                  "price_object_id",
                  "activity_object_id",
                  "relation",
                  "comparison",
                  "rows"
                ],
                "additionalProperties": false
              },
              {
                "type": "null"
              }
            ]
          },
          "sources": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "source": {
                  "type": "string"
                },
                "object_id": {
                  "$ref": "#/components/schemas/ObjectId"
                },
                "url": {
                  "type": "string"
                }
              },
              "required": [
                "source",
                "object_id",
                "url"
              ],
              "additionalProperties": false
            }
          },
          "rows": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "trade_date": {
                  "type": "string",
                  "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                },
                "volume": {
                  "$ref": "#/components/schemas/MarketActivityFact"
                },
                "amount": {
                  "$ref": "#/components/schemas/MarketActivityFact"
                }
              },
              "required": [
                "trade_date",
                "volume",
                "amount"
              ],
              "additionalProperties": false
            }
          },
          "completion_basis": {
            "$ref": "#/components/schemas/IndexSeriesCompletionBasis"
          },
          "observations": {
            "type": "array",
            "minItems": 1,
            "items": {
              "$ref": "#/components/schemas/MarketActivityObservation"
            }
          }
        },
        "required": [
          "schema_version",
          "series_id",
          "activity_id",
          "price_snapshot_id",
          "anchor_date",
          "window",
          "calendar_version",
          "calendar_dates",
          "source_policy_version",
          "parser_version",
          "pit_grade",
          "currency",
          "source_scope",
          "source_revision_relation",
          "source_revision_id",
          "binding",
          "sources",
          "rows",
          "completion_basis",
          "observations"
        ],
        "additionalProperties": false
      },
      "MarketActivityMarketSnapshot": {
        "type": "object",
        "properties": {
          "schema_version": {
            "const": "activity-facts-v1",
            "type": "string"
          },
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover"
            ]
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "price_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "anchor_date": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "window": {
            "$ref": "#/components/schemas/IndexSeriesWindow"
          },
          "calendar_version": {
            "type": "string"
          },
          "calendar_dates": {
            "type": "array",
            "items": {
              "type": "string",
              "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
            }
          },
          "source_policy_version": {
            "type": "string"
          },
          "parser_version": {
            "type": "string"
          },
          "pit_grade": {
            "const": "latest_only",
            "type": "string"
          },
          "currency": {
            "const": "CNY",
            "type": "string"
          },
          "source_scope": {
            "type": "string"
          },
          "source_revision_relation": {
            "const": "unknown",
            "type": "string"
          },
          "source_revision_id": {
            "type": "null"
          },
          "binding": {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "version": {
                    "type": "string"
                  },
                  "price_object_id": {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  "activity_object_id": {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  "relation": {
                    "type": "string",
                    "enum": [
                      "same_source_object",
                      "different_source_objects"
                    ]
                  },
                  "comparison": {
                    "const": "exact_available_values_match",
                    "type": "string"
                  },
                  "rows": {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "trade_date": {
                          "type": "string",
                          "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                        },
                        "price_locator": {
                          "type": "string"
                        },
                        "activity_locator": {
                          "type": "string"
                        }
                      },
                      "required": [
                        "trade_date",
                        "price_locator",
                        "activity_locator"
                      ],
                      "additionalProperties": false
                    }
                  }
                },
                "required": [
                  "version",
                  "price_object_id",
                  "activity_object_id",
                  "relation",
                  "comparison",
                  "rows"
                ],
                "additionalProperties": false
              },
              {
                "type": "null"
              }
            ]
          },
          "sources": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "source": {
                  "type": "string"
                },
                "object_id": {
                  "$ref": "#/components/schemas/ObjectId"
                },
                "url": {
                  "type": "string"
                }
              },
              "required": [
                "source",
                "object_id",
                "url"
              ],
              "additionalProperties": false
            }
          },
          "rows": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "trade_date": {
                  "type": "string",
                  "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                },
                "components": {
                  "type": "object",
                  "properties": {
                    "sse": {
                      "type": "array",
                      "minItems": 1,
                      "maxItems": 2,
                      "items": {
                        "$ref": "#/components/schemas/MarketActivityFact"
                      }
                    },
                    "szse": {
                      "type": "array",
                      "minItems": 1,
                      "maxItems": 2,
                      "items": {
                        "$ref": "#/components/schemas/MarketActivityFact"
                      }
                    },
                    "bse": {
                      "type": "array",
                      "minItems": 1,
                      "maxItems": 2,
                      "items": {
                        "$ref": "#/components/schemas/MarketActivityFact"
                      }
                    }
                  },
                  "required": [
                    "sse",
                    "szse",
                    "bse"
                  ],
                  "additionalProperties": false
                }
              },
              "required": [
                "trade_date",
                "components"
              ],
              "additionalProperties": false
            }
          },
          "completion_basis": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/IndexSeriesCompletionBasis"
              },
              {
                "$ref": "#/components/schemas/ThreeMarketCompletionBasis"
              }
            ]
          },
          "market_calendars": {
            "type": "object",
            "properties": {
              "sse": {
                "anyOf": [
                  {
                    "type": "array",
                    "items": {
                      "type": "string"
                    }
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "szse": {
                "anyOf": [
                  {
                    "type": "array",
                    "items": {
                      "type": "string"
                    }
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "bse": {
                "anyOf": [
                  {
                    "type": "array",
                    "items": {
                      "type": "string"
                    }
                  },
                  {
                    "type": "null"
                  }
                ]
              }
            },
            "required": [
              "sse",
              "szse",
              "bse"
            ],
            "additionalProperties": false
          },
          "observations": {
            "type": "array",
            "minItems": 1,
            "items": {
              "$ref": "#/components/schemas/MarketActivityObservation"
            }
          }
        },
        "required": [
          "schema_version",
          "series_id",
          "activity_id",
          "price_snapshot_id",
          "anchor_date",
          "window",
          "calendar_version",
          "calendar_dates",
          "source_policy_version",
          "parser_version",
          "pit_grade",
          "currency",
          "source_scope",
          "source_revision_relation",
          "source_revision_id",
          "binding",
          "sources",
          "rows",
          "completion_basis",
          "market_calendars",
          "observations"
        ],
        "additionalProperties": false
      },
      "MarketActivityObservedSource": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "source": {
            "type": "string"
          },
          "object_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "url": {
            "type": "string"
          },
          "started_at": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:\\d{2})$"
          },
          "completed_at": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:\\d{2})$"
          },
          "published_at": {
            "type": "null"
          }
        },
        "required": [
          "source",
          "object_id",
          "url",
          "started_at",
          "completed_at",
          "published_at"
        ]
      },
      "MarketActivityObservation": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "price_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "request_id": {
            "$ref": "#/components/schemas/RequestId"
          },
          "sources": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2200,
            "items": {
              "$ref": "#/components/schemas/MarketActivityObservedSource"
            }
          }
        },
        "required": [
          "series_id",
          "activity_id",
          "price_snapshot_id",
          "observation_id",
          "request_id",
          "sources"
        ]
      },
      "MarketActivityTwoMarketSnapshot": {
        "type": "object",
        "properties": {
          "schema_version": {
            "const": "activity-facts-v1",
            "type": "string"
          },
          "series_id": {
            "type": "string",
            "const": "cn-a-turnover-sse-szse"
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "price_snapshot_id": {
            "type": "null"
          },
          "anchor_date": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "window": {
            "$ref": "#/components/schemas/IndexSeriesWindow"
          },
          "calendar_version": {
            "type": "string"
          },
          "calendar_dates": {
            "type": "array",
            "items": {
              "type": "string",
              "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
            }
          },
          "source_policy_version": {
            "type": "string"
          },
          "parser_version": {
            "type": "string"
          },
          "pit_grade": {
            "const": "latest_only",
            "type": "string"
          },
          "currency": {
            "const": "CNY",
            "type": "string"
          },
          "source_scope": {
            "type": "string"
          },
          "source_revision_relation": {
            "const": "unknown",
            "type": "string"
          },
          "source_revision_id": {
            "type": "null"
          },
          "binding": {
            "type": "null"
          },
          "sources": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "source": {
                  "type": "string"
                },
                "object_id": {
                  "$ref": "#/components/schemas/ObjectId"
                },
                "url": {
                  "type": "string"
                }
              },
              "required": [
                "source",
                "object_id",
                "url"
              ],
              "additionalProperties": false
            }
          },
          "rows": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "trade_date": {
                  "type": "string",
                  "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                },
                "components": {
                  "type": "object",
                  "properties": {
                    "sse": {
                      "type": "array",
                      "minItems": 1,
                      "maxItems": 2,
                      "items": {
                        "$ref": "#/components/schemas/MarketActivityFact"
                      }
                    },
                    "szse": {
                      "type": "array",
                      "minItems": 1,
                      "maxItems": 2,
                      "items": {
                        "$ref": "#/components/schemas/MarketActivityFact"
                      }
                    }
                  },
                  "required": [
                    "sse",
                    "szse"
                  ],
                  "additionalProperties": false
                }
              },
              "required": [
                "trade_date",
                "components"
              ],
              "additionalProperties": false
            }
          },
          "completion_basis": {
            "$ref": "#/components/schemas/IndexSeriesCompletionBasis"
          },
          "market_calendars": {
            "type": "object",
            "properties": {
              "sse": {
                "anyOf": [
                  {
                    "type": "array",
                    "items": {
                      "type": "string"
                    }
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "szse": {
                "anyOf": [
                  {
                    "type": "array",
                    "items": {
                      "type": "string"
                    }
                  },
                  {
                    "type": "null"
                  }
                ]
              }
            },
            "required": [
              "sse",
              "szse"
            ],
            "additionalProperties": false
          },
          "observations": {
            "type": "array",
            "minItems": 1,
            "items": {
              "$ref": "#/components/schemas/MarketActivityObservation"
            }
          }
        },
        "required": [
          "schema_version",
          "series_id",
          "activity_id",
          "price_snapshot_id",
          "anchor_date",
          "window",
          "calendar_version",
          "calendar_dates",
          "source_policy_version",
          "parser_version",
          "pit_grade",
          "currency",
          "source_scope",
          "source_revision_relation",
          "source_revision_id",
          "binding",
          "sources",
          "rows",
          "completion_basis",
          "market_calendars",
          "observations"
        ],
        "additionalProperties": false
      },
      "OverviewPeriodicPolicy": {
        "type": "object",
        "properties": {
          "version": {
            "type": "string",
            "const": "overview-periodic-v1"
          },
          "timezone": {
            "type": "string",
            "const": "Asia/Shanghai"
          },
          "check_time": {
            "type": "string",
            "const": "07:00"
          },
          "daily_requests": {
            "type": "integer"
          },
          "daily_bytes": {
            "type": "integer"
          },
          "monthly_requests": {
            "type": "integer"
          },
          "monthly_bytes": {
            "type": "integer"
          },
          "charging": {
            "type": "string",
            "const": "response-limit-no-refund"
          },
          "ledger_version": {
            "type": "string",
            "const": "overview-periodic-ledger-v1"
          },
          "scope_id": {
            "type": "string",
            "pattern": "^[a-f0-9]{64}$"
          }
        },
        "required": [
          "version",
          "timezone",
          "check_time",
          "daily_requests",
          "daily_bytes",
          "monthly_requests",
          "monthly_bytes",
          "charging",
          "ledger_version",
          "scope_id"
        ],
        "additionalProperties": false
      },
      "ThreeMarketCalendarSource": {
        "type": "object",
        "properties": {
          "year": {
            "type": "integer",
            "enum": [
              2023,
              2024,
              2025,
              2026
            ]
          },
          "exchange": {
            "type": "string",
            "enum": [
              "sse",
              "szse",
              "bse"
            ]
          },
          "url": {
            "type": "string"
          },
          "evidence_kind": {
            "type": "string",
            "enum": [
              "web_tool_text",
              "http_original"
            ]
          },
          "evidence_sha256": {
            "$ref": "#/components/schemas/ObjectId"
          }
        },
        "required": [
          "year",
          "exchange",
          "url",
          "evidence_kind",
          "evidence_sha256"
        ],
        "additionalProperties": false
      },
      "ThreeMarketCompletionBasis": {
        "type": "object",
        "properties": {
          "rule": {
            "type": "string",
            "const": "exchange_weekdays_excluding_announced_full_day_closures_before_shanghai_today"
          },
          "timezone": {
            "type": "string",
            "const": "Asia/Shanghai"
          },
          "exclude_anchor_day": {
            "type": "boolean",
            "const": true
          },
          "supported_years": {
            "type": "array",
            "items": {
              "type": "integer",
              "enum": [
                2023,
                2024,
                2025,
                2026
              ]
            },
            "minItems": 4,
            "maxItems": 4
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/ThreeMarketCalendarSource"
            },
            "minItems": 12,
            "maxItems": 12
          },
          "limitations": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        },
        "required": [
          "rule",
          "timezone",
          "exclude_anchor_day",
          "supported_years",
          "sources",
          "limitations"
        ],
        "additionalProperties": false
      },
      "MarketActivityAnchors": {
        "type": "object",
        "properties": {
          "sse_szse": {
            "type": [
              "string",
              "null"
            ],
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "sse_szse_bse": {
            "type": [
              "string",
              "null"
            ],
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          }
        },
        "required": [
          "sse_szse",
          "sse_szse_bse"
        ],
        "additionalProperties": false
      },
      "MarketActivitySeriesId": {
        "type": "string",
        "enum": [
          "sse:000001:price",
          "szse:399001:price",
          "szse:399006:price",
          "sse:000688:price",
          "cn-a-turnover",
          "cn-a-turnover-sse-szse"
        ]
      },
      "BusinessError": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string"
              },
              "message": {
                "type": "string"
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "OverviewUpdateStatus": {
        "type": "object",
        "properties": {
          "revision": {
            "type": "integer"
          },
          "state": {
            "type": "string",
            "enum": [
              "idle",
              "running",
              "failed",
              "blocked"
            ]
          },
          "reason": {
            "type": [
              "string",
              "null"
            ],
            "maxLength": 100,
            "pattern": "^[a-z_]+$"
          },
          "market_anchor_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "server_day": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "next_check_at": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+08:00$"
          },
          "resume_at": {
            "type": [
              "string",
              "null"
            ],
            "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+08:00$"
          },
          "daily": {
            "$ref": "#/components/schemas/OverviewBudgetCounter"
          },
          "monthly": {
            "$ref": "#/components/schemas/OverviewBudgetCounter"
          },
          "reserved": {
            "$ref": "#/components/schemas/OverviewBudgetCounter"
          },
          "warning": {
            "type": "boolean"
          },
          "daily_resets_at": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+08:00$"
          },
          "monthly_resets_at": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+08:00$"
          },
          "market_anchors": {
            "$ref": "#/components/schemas/MarketActivityAnchors"
          }
        },
        "required": [
          "revision",
          "state",
          "reason",
          "market_anchor_date",
          "server_day",
          "next_check_at",
          "resume_at",
          "daily",
          "monthly",
          "reserved",
          "warning",
          "daily_resets_at",
          "monthly_resets_at"
        ],
        "additionalProperties": false
      },
      "OverviewBudgetCounter": {
        "type": "object",
        "properties": {
          "requests": {
            "type": "integer"
          },
          "bytes": {
            "type": "integer"
          }
        },
        "required": [
          "requests",
          "bytes"
        ],
        "additionalProperties": false
      },
      "MarketActivityDescriptor": {
        "type": "object",
        "properties": {
          "endpoint": {
            "type": "string",
            "minLength": 1
          },
          "service_id": {
            "const": "thewolf-local-service",
            "type": "string"
          },
          "service_version": {
            "type": "string",
            "minLength": 1
          },
          "contract_version": {
            "const": "3.0.0",
            "type": "string"
          },
          "contract_sha256": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "data_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "identity_format": {
            "const": "wolf-activity-config-v1",
            "type": "string"
          },
          "feature_version": {
            "const": "market-activity-v1",
            "type": "string"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "price_index_config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "activity_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "series": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "sse:000001:price",
                "szse:399001:price",
                "szse:399006:price",
                "sse:000688:price",
                "cn-a-turnover",
                "cn-a-turnover-sse-szse"
              ]
            }
          },
          "write_series": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "sse:000001:price",
                "szse:399001:price",
                "szse:399006:price",
                "sse:000688:price",
                "cn-a-turnover",
                "cn-a-turnover-sse-szse"
              ]
            }
          },
          "startup_series": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "sse:000001:price",
                "szse:399001:price",
                "szse:399006:price",
                "sse:000688:price",
                "cn-a-turnover",
                "cn-a-turnover-sse-szse"
              ]
            },
            "maxItems": 6
          },
          "blocked_series": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "series_id": {
                  "type": "string",
                  "enum": [
                    "sse:000001:price",
                    "szse:399001:price",
                    "szse:399006:price",
                    "sse:000688:price",
                    "cn-a-turnover",
                    "cn-a-turnover-sse-szse"
                  ]
                },
                "evidence_id": {
                  "$ref": "#/components/schemas/ObjectId"
                },
                "reason": {
                  "const": "source_withdrawn",
                  "type": "string"
                }
              },
              "required": [
                "series_id",
                "evidence_id",
                "reason"
              ],
              "additionalProperties": false
            }
          },
          "policy": {
            "$ref": "#/components/schemas/MarketActivityPolicy"
          }
        },
        "required": [
          "endpoint",
          "service_id",
          "service_version",
          "contract_version",
          "contract_sha256",
          "data_scope_id",
          "identity_format",
          "feature_version",
          "config_id",
          "price_index_config_id",
          "activity_scope_id",
          "series",
          "write_series",
          "startup_series",
          "blocked_series",
          "policy"
        ],
        "additionalProperties": false
      },
      "IndexSeriesDescriptor": {
        "type": "object",
        "properties": {
          "endpoint": {
            "type": "string",
            "minLength": 1
          },
          "service_id": {
            "const": "thewolf-local-service",
            "type": "string"
          },
          "service_version": {
            "type": "string",
            "minLength": 1
          },
          "contract_version": {
            "const": "3.0.0",
            "type": "string"
          },
          "contract_sha256": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "data_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "identity_format": {
            "type": "string",
            "const": "wolf-index-config-v2"
          },
          "feature_version": {
            "type": "string",
            "const": "index-series-v2"
          },
          "write_indices": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesId"
            },
            "maxItems": 6
          },
          "startup_indices": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesId"
            },
            "maxItems": 6
          },
          "policy": {
            "$ref": "#/components/schemas/IndexSeriesPolicy"
          }
        },
        "required": [
          "endpoint",
          "service_id",
          "service_version",
          "contract_version",
          "contract_sha256",
          "data_scope_id",
          "config_id",
          "identity_format",
          "feature_version",
          "write_indices",
          "startup_indices",
          "policy"
        ],
        "additionalProperties": false
      },
      "EtfBasis": {
        "type": "object",
        "properties": {
          "url": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2048,
            "pattern": "^https://"
          },
          "report_date": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "published_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "locator": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500
          }
        },
        "required": [
          "url",
          "report_date",
          "published_date",
          "locator"
        ],
        "additionalProperties": false
      },
      "EtfMember": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "code": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "manager": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "exchange": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "tracking_index": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "index_id": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "group": {
            "type": "string",
            "minLength": 1,
            "maxLength": 80
          },
          "enabled_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "disabled_date": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "basis": {
            "$ref": "#/components/schemas/EtfBasis"
          }
        },
        "required": [
          "id",
          "code",
          "name",
          "manager",
          "exchange",
          "tracking_index",
          "index_id",
          "group",
          "enabled_date",
          "disabled_date",
          "basis"
        ],
        "additionalProperties": false
      },
      "EtfSource": {
        "type": "object",
        "properties": {
          "object_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "publisher": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "channel": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "url": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2048,
            "pattern": "^https://"
          },
          "retrieved_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "published_at": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
              },
              {
                "type": "null"
              }
            ]
          },
          "locator": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000
          },
          "original_unit": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "precision": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          }
        },
        "required": [
          "object_id",
          "publisher",
          "channel",
          "url",
          "retrieved_at",
          "published_at",
          "locator",
          "original_unit",
          "precision"
        ],
        "additionalProperties": false
      },
      "EtfMetrics": {
        "type": "object",
        "properties": {
          "shares": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "comparable_previous": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "delta": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "change_rate": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "amount": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "nav": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "close": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "turnover": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "volume": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "net_assets": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "premium": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "turnover_ratio": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "adjustment": {
            "type": "boolean"
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[a-z_]{1,100}$"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "shares",
          "comparable_previous",
          "delta",
          "change_rate",
          "amount",
          "nav",
          "close",
          "turnover",
          "volume",
          "net_assets",
          "premium",
          "turnover_ratio",
          "date",
          "adjustment",
          "reason"
        ],
        "additionalProperties": false
      },
      "EtfCondition": {
        "type": "object",
        "properties": {
          "mean": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "standard_deviation": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "upper": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "lower": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "positive_ratio": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "negative_ratio": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "threshold": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "positive_count": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0
              },
              {
                "type": "null"
              }
            ]
          },
          "negative_count": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0
              },
              {
                "type": "null"
              }
            ]
          },
          "denominator": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0
              },
              {
                "type": "null"
              }
            ]
          },
          "state": {
            "type": "string",
            "enum": [
              "insufficient",
              "parameters_pending",
              "evaluated"
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[a-z_]{1,100}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "incoming": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ]
          },
          "outgoing": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "mean",
          "standard_deviation",
          "upper",
          "lower",
          "positive_ratio",
          "negative_ratio",
          "threshold",
          "positive_count",
          "negative_count",
          "denominator",
          "state",
          "reason",
          "incoming",
          "outgoing"
        ],
        "additionalProperties": false
      },
      "EtfExclusion": {
        "type": "object",
        "properties": {
          "member_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "reason": {
            "type": "string",
            "pattern": "^[a-z_]{1,100}$"
          }
        },
        "required": [
          "member_id",
          "reason"
        ],
        "additionalProperties": false
      },
      "EtfEvaluation": {
        "type": "object",
        "properties": {
          "result_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "state": {
            "type": "string",
            "enum": [
              "insufficient",
              "parameters_pending",
              "abnormal_subscription",
              "abnormal_redemption",
              "not_triggered"
            ]
          },
          "amount": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "partial": {
            "type": "boolean"
          },
          "active_count": {
            "type": "integer",
            "minimum": 0
          },
          "ready_count": {
            "type": "integer",
            "minimum": 0
          },
          "valid_count": {
            "type": "integer",
            "minimum": 0
          },
          "valid_ids": {
            "type": "array",
            "items": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
            }
          },
          "exclusions": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfExclusion"
            }
          },
          "c1": {
            "$ref": "#/components/schemas/EtfCondition"
          },
          "c2": {
            "$ref": "#/components/schemas/EtfCondition"
          },
          "pool_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "rule_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "input_version": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "calculated_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "selection_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "group_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PublicDigest"
              },
              {
                "type": "null"
              }
            ]
          },
          "mode": {
            "type": "string",
            "enum": [
              "original",
              "current"
            ]
          }
        },
        "required": [
          "result_id",
          "date",
          "state",
          "amount",
          "partial",
          "active_count",
          "ready_count",
          "valid_count",
          "valid_ids",
          "exclusions",
          "c1",
          "c2",
          "pool_version",
          "rule_version",
          "input_version",
          "calculated_at",
          "selection_at",
          "group_id",
          "mode"
        ],
        "additionalProperties": false
      },
      "EtfAdmission": {
        "type": "object",
        "properties": {
          "id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "member_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "first_qualified_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "checked_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "start": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "end": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "required_days": {
            "type": "integer",
            "minimum": 321
          },
          "input_version": {
            "$ref": "#/components/schemas/PublicDigest"
          }
        },
        "required": [
          "id",
          "member_id",
          "first_qualified_at",
          "checked_at",
          "start",
          "end",
          "required_days",
          "input_version"
        ],
        "additionalProperties": false
      },
      "EtfMemberPoint": {
        "type": "object",
        "properties": {
          "metrics": {
            "$ref": "#/components/schemas/EtfMetrics"
          },
          "source_ids": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/PublicDigest"
            }
          },
          "adjustment_detail": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/EtfAdjustmentDetail"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "metrics",
          "source_ids",
          "adjustment_detail"
        ],
        "additionalProperties": false
      },
      "EtfMemberView": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "code": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "manager": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "exchange": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "tracking_index": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "index_id": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "group": {
            "type": "string",
            "minLength": 1,
            "maxLength": 80
          },
          "enabled_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "disabled_date": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "basis": {
            "$ref": "#/components/schemas/EtfBasis"
          },
          "group_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "active": {
            "type": "boolean"
          },
          "admission": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/EtfAdmission"
              },
              {
                "type": "null"
              }
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[a-z_]{1,100}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "metrics": {
            "$ref": "#/components/schemas/EtfMetrics"
          },
          "amount_5": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "amount_20": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "series": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfMemberPoint"
            }
          },
          "input_basis": {
            "type": "string",
            "enum": [
              "recorded_inputs",
              "posthoc_inputs"
            ]
          },
          "input_version": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "input_selected_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          }
        },
        "required": [
          "id",
          "code",
          "name",
          "manager",
          "exchange",
          "tracking_index",
          "index_id",
          "group",
          "enabled_date",
          "disabled_date",
          "basis",
          "group_id",
          "active",
          "admission",
          "reason",
          "metrics",
          "amount_5",
          "amount_20",
          "series",
          "input_basis",
          "input_version",
          "input_selected_at"
        ],
        "additionalProperties": false
      },
      "EtfGroup": {
        "type": "object",
        "properties": {
          "id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 80
          },
          "member_ids": {
            "type": "array",
            "items": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
            }
          }
        },
        "required": [
          "id",
          "name",
          "member_ids"
        ],
        "additionalProperties": false
      },
      "EtfStreak": {
        "type": "object",
        "properties": {
          "state": {
            "type": "string",
            "enum": [
              "parameters_pending",
              "insufficient",
              "not_met",
              "met"
            ]
          },
          "direction": {
            "anyOf": [
              {
                "type": "string",
                "enum": [
                  "subscription",
                  "redemption"
                ]
              },
              {
                "type": "null"
              }
            ]
          },
          "days": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0
              },
              {
                "type": "null"
              }
            ]
          },
          "amount": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "state",
          "direction",
          "days",
          "amount"
        ],
        "additionalProperties": false
      },
      "EtfSummary": {
        "type": "object",
        "properties": {
          "evaluation": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/EtfEvaluation"
              },
              {
                "type": "null"
              }
            ]
          },
          "amount_5": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "amount_20": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "streak": {
            "$ref": "#/components/schemas/EtfStreak"
          }
        },
        "required": [
          "evaluation",
          "amount_5",
          "amount_20",
          "streak"
        ],
        "additionalProperties": false
      },
      "EtfPoint": {
        "type": "object",
        "properties": {
          "date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "state": {
            "type": "string",
            "enum": [
              "unrecorded",
              "insufficient",
              "parameters_pending",
              "abnormal_subscription",
              "abnormal_redemption",
              "not_triggered"
            ]
          },
          "evaluation": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/EtfEvaluation"
              },
              {
                "type": "null"
              }
            ]
          },
          "cumulative": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "date",
          "state",
          "evaluation",
          "cumulative"
        ],
        "additionalProperties": false
      },
      "EtfHolder": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "shares": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "percentage": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "classification": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1,
                "maxLength": 200
              },
              {
                "type": "null"
              }
            ]
          },
          "classification_basis": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1,
                "maxLength": 1000
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "name",
          "shares",
          "percentage",
          "classification",
          "classification_basis"
        ],
        "additionalProperties": false
      },
      "EtfDisclosure": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "member_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "report_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "published_date": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "source_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "locator": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000
          },
          "state": {
            "type": "string",
            "enum": [
              "disclosed",
              "not_disclosed"
            ]
          },
          "holders": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfHolder"
            }
          },
          "note": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000
          },
          "url": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2048,
            "pattern": "^https://"
          },
          "retrieved_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "known_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "knowledge": {
            "type": "string",
            "enum": [
              "later_comparison",
              "published_by_evaluation_day"
            ]
          },
          "publication_unknown": {
            "type": "boolean"
          }
        },
        "required": [
          "id",
          "member_id",
          "report_date",
          "published_date",
          "source_id",
          "locator",
          "state",
          "holders",
          "note",
          "url",
          "retrieved_at",
          "known_date",
          "knowledge",
          "publication_unknown"
        ],
        "additionalProperties": false
      },
      "EtfEvent": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "member_ids": {
            "type": "array",
            "items": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
            }
          },
          "occurred_start": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "occurred_end": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "published_date": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "source_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "locator": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000
          },
          "description": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2000
          },
          "subjects": {
            "type": "array",
            "items": {
              "type": "string",
              "minLength": 1,
              "maxLength": 200
            }
          },
          "marker_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "marker_kind": {
            "type": "string",
            "enum": [
              "occurrence",
              "announcement"
            ]
          },
          "url": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2048,
            "pattern": "^https://"
          },
          "retrieved_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "known_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "knowledge": {
            "type": "string",
            "enum": [
              "later_comparison",
              "published_by_evaluation_day"
            ]
          },
          "publication_unknown": {
            "type": "boolean"
          }
        },
        "required": [
          "id",
          "member_ids",
          "occurred_start",
          "occurred_end",
          "published_date",
          "source_id",
          "locator",
          "description",
          "subjects",
          "marker_date",
          "marker_kind",
          "url",
          "retrieved_at",
          "known_date",
          "knowledge",
          "publication_unknown"
        ],
        "additionalProperties": false
      },
      "EtfRule": {
        "type": "object",
        "properties": {
          "version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "effective_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "confirmed_at": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
              },
              {
                "type": "null"
              }
            ]
          },
          "confirmation": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1,
                "maxLength": 1000
              },
              {
                "type": "null"
              }
            ]
          },
          "window": {
            "type": "integer",
            "minimum": 2
          },
          "k": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "min_in": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "min_out": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "direction_ratio": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "streak_days": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 2
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "version",
          "effective_date",
          "confirmed_at",
          "confirmation",
          "window",
          "k",
          "min_in",
          "min_out",
          "direction_ratio",
          "streak_days"
        ],
        "additionalProperties": false
      },
      "EtfPool": {
        "type": "object",
        "properties": {
          "version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "hash": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "effective_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "confirmed_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "change": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000
          }
        },
        "required": [
          "version",
          "hash",
          "effective_date",
          "confirmed_at",
          "change"
        ],
        "additionalProperties": false
      },
      "EtfIndexContext": {
        "type": "object",
        "properties": {
          "index_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "formula_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "return_1": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "return_5": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "input_basis": {
            "type": "string",
            "const": "posthoc_context"
          },
          "calculated_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          }
        },
        "required": [
          "index_id",
          "snapshot_id",
          "formula_version",
          "date",
          "return_1",
          "return_5",
          "input_basis",
          "calculated_at"
        ],
        "additionalProperties": false
      },
      "EtfMarketContext": {
        "type": "object",
        "properties": {
          "series_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "activity_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "formula_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "date": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "scope_label": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "turnover": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "ratio_20": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
                "maxLength": 400
              },
              {
                "type": "null"
              }
            ]
          },
          "input_basis": {
            "type": "string",
            "const": "posthoc_context"
          },
          "calculated_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          }
        },
        "required": [
          "series_id",
          "activity_id",
          "formula_version",
          "date",
          "scope_label",
          "turnover",
          "ratio_20",
          "input_basis",
          "calculated_at"
        ],
        "additionalProperties": false
      },
      "EtfContext": {
        "type": "object",
        "properties": {
          "indices": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfIndexContext"
            }
          },
          "market": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/EtfMarketContext"
              },
              {
                "type": "null"
              }
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[a-z_]{1,100}$"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "indices",
          "market",
          "reason"
        ],
        "additionalProperties": false
      },
      "EtfDataStatus": {
        "type": "object",
        "properties": {
          "state": {
            "type": "string",
            "enum": [
              "unrecorded",
              "insufficient",
              "parameters_pending",
              "abnormal_subscription",
              "abnormal_redemption",
              "not_triggered"
            ]
          },
          "input_basis": {
            "type": "string",
            "enum": [
              "recorded_inputs",
              "posthoc_inputs"
            ]
          },
          "evidence_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "history_first": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "history_last": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "original_recorded": {
            "type": "boolean"
          },
          "parameters_confirmed": {
            "type": "boolean"
          },
          "required_days": {
            "type": "integer",
            "minimum": 321
          },
          "complete_amount_through": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "state",
          "input_basis",
          "evidence_version",
          "history_first",
          "history_last",
          "original_recorded",
          "parameters_confirmed",
          "required_days",
          "complete_amount_through"
        ],
        "additionalProperties": false
      },
      "EtfView": {
        "type": "object",
        "properties": {
          "schema_version": {
            "type": "string",
            "const": "etf-flow-view-v2"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "formula_version": {
            "type": "string",
            "const": "etf-flow-v1"
          },
          "mode": {
            "type": "string",
            "enum": [
              "original",
              "current"
            ]
          },
          "end": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "period": {
            "type": "integer",
            "enum": [
              20,
              60,
              120,
              260
            ]
          },
          "group_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PublicDigest"
              },
              {
                "type": "null"
              }
            ]
          },
          "selection_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "selected_member_ids": {
            "type": "array",
            "items": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
            }
          },
          "pool_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "rule_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "input_version": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "calculated_at": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
              },
              {
                "type": "null"
              }
            ]
          },
          "server_day": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "groups": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfGroup"
            }
          },
          "members": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfMemberView"
            }
          },
          "summary": {
            "$ref": "#/components/schemas/EtfSummary"
          },
          "series": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfPoint"
            }
          },
          "history": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfEvaluation"
            }
          },
          "disclosures": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfDisclosure"
            }
          },
          "events": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfEvent"
            }
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfSource"
            }
          },
          "context": {
            "$ref": "#/components/schemas/EtfContext"
          },
          "data_status": {
            "$ref": "#/components/schemas/EtfDataStatus"
          },
          "rule": {
            "$ref": "#/components/schemas/EtfRule"
          },
          "pool": {
            "$ref": "#/components/schemas/EtfPool"
          }
        },
        "required": [
          "schema_version",
          "snapshot_id",
          "formula_version",
          "mode",
          "end",
          "period",
          "group_id",
          "selection_at",
          "selected_member_ids",
          "pool_version",
          "rule_version",
          "input_version",
          "calculated_at",
          "server_day",
          "groups",
          "members",
          "summary",
          "series",
          "history",
          "disclosures",
          "events",
          "sources",
          "context",
          "data_status",
          "rule",
          "pool"
        ],
        "additionalProperties": false
      },
      "EtfOperation": {
        "type": "object",
        "properties": {
          "request_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          },
          "operation_key": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "plan_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "expected_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PublicDigest"
              },
              {
                "type": "null"
              }
            ]
          },
          "state": {
            "type": "string",
            "enum": [
              "queued",
              "running",
              "completed",
              "failed",
              "interrupted"
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[a-z_]{1,100}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PublicDigest"
              },
              {
                "type": "null"
              }
            ]
          },
          "created_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "updated_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "batch_id": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[a-f0-9]{32}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "lease_closed": {
            "type": "boolean"
          },
          "recovered_from_instance": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PublicInstanceId"
              },
              {
                "type": "null"
              }
            ]
          },
          "serving_instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          },
          "serving_config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "recovery_required": {
            "type": "boolean"
          }
        },
        "required": [
          "request_id",
          "config_id",
          "instance_id",
          "operation_key",
          "plan_id",
          "expected_snapshot_id",
          "state",
          "reason",
          "snapshot_id",
          "created_at",
          "updated_at",
          "batch_id",
          "lease_closed",
          "recovered_from_instance",
          "serving_instance_id",
          "serving_config_id",
          "recovery_required"
        ],
        "additionalProperties": false
      },
      "EtfUsage": {
        "type": "object",
        "properties": {
          "grant_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "requests": {
            "type": "integer",
            "minimum": 0
          },
          "reserved_bytes": {
            "type": "integer",
            "minimum": 0
          },
          "actual_bytes": {
            "type": "integer",
            "minimum": 0
          },
          "unknown_attempts": {
            "type": "integer",
            "minimum": 0
          },
          "max_requests": {
            "type": "integer",
            "minimum": 0
          },
          "max_bytes": {
            "type": "integer",
            "minimum": 0
          },
          "expires_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          }
        },
        "required": [
          "grant_id",
          "requests",
          "reserved_bytes",
          "actual_bytes",
          "unknown_attempts",
          "max_requests",
          "max_bytes",
          "expires_at"
        ],
        "additionalProperties": false
      },
      "EtfPlan": {
        "type": "object",
        "properties": {
          "id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "start": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "end": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "member_ids": {
            "type": "array",
            "items": {
              "type": "string",
              "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
            }
          },
          "request_count": {
            "type": "integer",
            "minimum": 0
          },
          "cached_request_count": {
            "type": "integer",
            "minimum": 0
          },
          "reserved_bytes": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "id",
          "start",
          "end",
          "member_ids",
          "request_count",
          "cached_request_count",
          "reserved_bytes"
        ],
        "additionalProperties": false
      },
      "EtfUnresolved": {
        "type": "object",
        "properties": {
          "request_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          }
        },
        "required": [
          "request_id",
          "config_id",
          "instance_id"
        ],
        "additionalProperties": false
      },
      "EtfCurrent": {
        "type": "object",
        "properties": {
          "snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PublicDigest"
              },
              {
                "type": "null"
              }
            ]
          },
          "selection_at": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
              },
              {
                "type": "null"
              }
            ]
          },
          "end": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "server_day": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "configuration_pending": {
            "type": "boolean"
          },
          "configuration_reason": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[a-z_]{1,100}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "members": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfMember"
            }
          },
          "pool_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "rule_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "initialized": {
            "type": "boolean"
          },
          "write_enabled": {
            "type": "boolean"
          },
          "blocked_reason": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[a-z_]{1,100}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "usage": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/EtfUsage"
              },
              {
                "type": "null"
              }
            ]
          },
          "plan": {
            "$ref": "#/components/schemas/EtfPlan"
          },
          "operation": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/EtfOperation"
              },
              {
                "type": "null"
              }
            ]
          },
          "unresolved": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfUnresolved"
            }
          }
        },
        "required": [
          "snapshot_id",
          "selection_at",
          "end",
          "server_day",
          "configuration_pending",
          "configuration_reason",
          "members",
          "pool_version",
          "rule_version",
          "initialized",
          "write_enabled",
          "blocked_reason",
          "usage",
          "plan",
          "operation",
          "unresolved"
        ],
        "additionalProperties": false
      },
      "EtfEvidence": {
        "type": "object",
        "properties": {
          "snapshot_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "object_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "bytes": {
            "type": "integer",
            "minimum": 0
          },
          "references": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/EtfSource"
            }
          }
        },
        "required": [
          "snapshot_id",
          "object_id",
          "bytes",
          "references"
        ],
        "additionalProperties": false
      },
      "EtfUpdateBody": {
        "type": "object",
        "properties": {
          "expected_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PublicDigest"
              },
              {
                "type": "null"
              }
            ]
          },
          "plan_id": {
            "$ref": "#/components/schemas/PublicDigest"
          }
        },
        "required": [
          "expected_snapshot_id",
          "plan_id"
        ],
        "additionalProperties": false
      },
      "EtfError": {
        "type": "object",
        "properties": {
          "detail": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "pattern": "^[a-z_]{1,100}$"
              },
              "message": {
                "type": "string",
                "minLength": 1,
                "maxLength": 500
              }
            },
            "required": [
              "code",
              "message"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "detail"
        ],
        "additionalProperties": false
      },
      "EtfDescriptor": {
        "type": "object",
        "properties": {
          "endpoint": {
            "type": "string",
            "pattern": "^http://127\\.0\\.0\\.1:[1-9][0-9]{0,4}$"
          },
          "service_id": {
            "type": "string",
            "const": "thewolf-local-service"
          },
          "service_version": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "contract_version": {
            "type": "string",
            "const": "3.0.0"
          },
          "contract_sha256": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "data_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "feature_version": {
            "type": "string",
            "const": "etf-flow-v1"
          },
          "identity_version": {
            "type": "string",
            "const": "wolf-etf-flow-config-v1"
          },
          "etf_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "configuration_hash": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "evidence_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "write_enabled": {
            "type": "boolean"
          },
          "grant_id": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "refresh_revision": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "endpoint",
          "service_id",
          "service_version",
          "contract_version",
          "contract_sha256",
          "data_scope_id",
          "feature_version",
          "identity_version",
          "etf_scope_id",
          "config_id",
          "configuration_hash",
          "evidence_version",
          "write_enabled",
          "grant_id",
          "refresh_revision"
        ],
        "additionalProperties": false
      },
      "EtfReady": {
        "type": "object",
        "properties": {
          "service_id": {
            "type": "string",
            "const": "thewolf-local-service"
          },
          "service_version": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "contract_version": {
            "type": "string",
            "const": "3.0.0"
          },
          "contract_sha256": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "data_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "feature_version": {
            "type": "string",
            "const": "etf-flow-v1"
          },
          "identity_version": {
            "type": "string",
            "const": "wolf-etf-flow-config-v1"
          },
          "etf_scope_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "config_id": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "configuration_hash": {
            "$ref": "#/components/schemas/PublicDigest"
          },
          "evidence_version": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
          },
          "write_enabled": {
            "type": "boolean"
          },
          "grant_id": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "refresh_revision": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "status": {
            "type": "string",
            "const": "ready"
          },
          "instance_id": {
            "$ref": "#/components/schemas/PublicInstanceId"
          }
        },
        "required": [
          "service_id",
          "service_version",
          "contract_version",
          "contract_sha256",
          "data_scope_id",
          "feature_version",
          "identity_version",
          "etf_scope_id",
          "config_id",
          "configuration_hash",
          "evidence_version",
          "write_enabled",
          "grant_id",
          "refresh_revision",
          "status",
          "instance_id"
        ],
        "additionalProperties": false
      },
      "EtfAdjustmentDetail": {
        "type": "object",
        "properties": {
          "kind": {
            "type": "string",
            "enum": [
              "normal",
              "adjustment"
            ]
          },
          "start": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "end": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
          },
          "factor": {
            "type": "string",
            "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
            "maxLength": 400
          },
          "tail": {
            "type": "string",
            "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",
            "maxLength": 400
          },
          "confirmed_at": {
            "type": "string",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
          },
          "confirmation": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000
          },
          "source_ids": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/PublicDigest"
            },
            "minItems": 1
          }
        },
        "required": [
          "kind",
          "start",
          "end",
          "factor",
          "tail",
          "confirmed_at",
          "confirmation",
          "source_ids"
        ],
        "additionalProperties": false
      },
      "CompactIndexDefinition": {
        "type": "object",
        "properties": {
          "unit": {
            "type": "string",
            "enum": [
              "%",
              "点"
            ]
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "adjacent-expected-close-pct-half-up-v1",
              "period-close-pct-half-up-v1",
              "trading-window-close-pct-v1",
              "natural-year-close-pct-v1",
              "close-sma-half-up-4-v1"
            ]
          },
          "parameters": {
            "$ref": "#/components/schemas/IndexSeriesCalculationParameters"
          }
        },
        "required": [
          "unit",
          "formula_version",
          "parameters"
        ],
        "additionalProperties": false
      },
      "CompactIndexScalar": {
        "type": "object",
        "properties": {
          "definition": {
            "type": "integer",
            "enum": [
              0,
              1,
              2,
              3,
              4,
              5,
              6,
              7,
              8,
              9,
              10,
              11,
              12,
              13,
              14,
              15,
              16,
              17,
              18,
              19,
              20,
              21,
              22,
              23,
              24,
              25,
              26,
              27,
              28,
              29,
              30,
              31
            ]
          },
          "value": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^-?[0-9]+\\.[0-9]{2}([0-9]{2})?$",
                "maxLength": 64
              },
              {
                "type": "null"
              }
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string",
                "enum": [
                  "insufficient_samples",
                  "missing_previous_close",
                  "missing_year_baseline"
                ]
              },
              {
                "type": "null"
              }
            ]
          },
          "start": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/Day"
              },
              {
                "type": "null"
              }
            ]
          },
          "end": {
            "$ref": "#/components/schemas/Day"
          }
        },
        "required": [
          "definition",
          "value",
          "reason",
          "start",
          "end"
        ],
        "additionalProperties": false
      },
      "CompactActivityDefinition": {
        "type": "object",
        "properties": {
          "unit": {
            "type": "string"
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "market-activity-calculations-v1",
              "market-activity-calculations-sse-szse-v1"
            ]
          },
          "parameters": {
            "type": "object",
            "properties": {
              "field": {
                "type": "string"
              },
              "frequency": {
                "type": "string"
              },
              "operation": {
                "type": "string"
              },
              "period": {
                "type": "string"
              }
            },
            "required": [
              "field",
              "frequency",
              "operation",
              "period"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "unit",
          "formula_version",
          "parameters"
        ],
        "additionalProperties": false
      },
      "CompactActivityScalar": {
        "type": "object",
        "properties": {
          "definition": {
            "type": "integer",
            "enum": [
              0,
              1,
              2,
              3,
              4,
              5,
              6,
              7,
              8,
              9,
              10,
              11,
              12,
              13,
              14,
              15,
              16,
              17,
              18,
              19,
              20,
              21,
              22,
              23,
              24,
              25,
              26,
              27,
              28,
              29,
              30,
              31,
              32,
              33,
              34,
              35,
              36,
              37,
              38,
              39,
              40,
              41,
              42,
              43,
              44,
              45,
              46,
              47,
              48,
              49,
              50,
              51,
              52,
              53,
              54,
              55,
              56,
              57,
              58,
              59,
              60,
              61,
              62,
              63
            ]
          },
          "value": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "reason": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "start": {
            "anyOf": [
              {
                "type": "string",
                "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
              },
              {
                "type": "null"
              }
            ]
          },
          "end": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "complete": {
            "type": "boolean"
          },
          "incomplete_reasons": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        },
        "required": [
          "definition",
          "value",
          "reason",
          "start",
          "end",
          "complete",
          "incomplete_reasons"
        ],
        "additionalProperties": false
      },
      "CompactIndexBar": {
        "type": "object",
        "properties": {
          "period_start": {
            "$ref": "#/components/schemas/Day"
          },
          "period_end": {
            "$ref": "#/components/schemas/Day"
          },
          "start": {
            "$ref": "#/components/schemas/Day"
          },
          "end": {
            "$ref": "#/components/schemas/Day"
          },
          "open": {
            "type": "string",
            "pattern": "^[0-9]+\\.[0-9]{2}([0-9]{2})?$",
            "maxLength": 45
          },
          "high": {
            "type": "string",
            "pattern": "^[0-9]+\\.[0-9]{2}([0-9]{2})?$",
            "maxLength": 45
          },
          "low": {
            "type": "string",
            "pattern": "^[0-9]+\\.[0-9]{2}([0-9]{2})?$",
            "maxLength": 45
          },
          "close": {
            "type": "string",
            "pattern": "^[0-9]+\\.[0-9]{2}([0-9]{2})?$",
            "maxLength": 45
          },
          "sample_count": {
            "type": "integer"
          },
          "complete": {
            "type": "boolean"
          },
          "incomplete_reasons": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "window_start_truncated",
                "period_in_progress",
                "calendar_unknown"
              ]
            },
            "maxItems": 3
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "raw-daily-price-v1",
              "calendar-ohlc-v1"
            ]
          },
          "change_pct": {
            "$ref": "#/components/schemas/CompactIndexScalar"
          },
          "ma": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/CompactIndexScalar"
            },
            "maxItems": 8
          }
        },
        "required": [
          "period_start",
          "period_end",
          "start",
          "end",
          "open",
          "high",
          "low",
          "close",
          "sample_count",
          "complete",
          "incomplete_reasons",
          "formula_version",
          "change_pct",
          "ma"
        ],
        "additionalProperties": false
      },
      "CompactIndexSeries": {
        "type": "object",
        "properties": {
          "frequency": {
            "type": "string",
            "enum": [
              "daily",
              "weekly",
              "monthly"
            ]
          },
          "ma_availability": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesCalculationAvailability"
            },
            "maxItems": 8
          },
          "rows": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/CompactIndexBar"
            },
            "maxItems": 1100
          }
        },
        "required": [
          "frequency",
          "ma_availability",
          "rows"
        ],
        "additionalProperties": false
      },
      "CompactIndexCalculations": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "formula_version": {
            "type": "string",
            "const": "index-price-calculations-v1"
          },
          "calendar_version": {
            "type": "string",
            "const": "cn-indices-sse-szse-2023-2026-v1"
          },
          "anchor_date": {
            "$ref": "#/components/schemas/Day"
          },
          "pit_grade": {
            "type": "string",
            "const": "latest_only"
          },
          "unit": {
            "type": "string",
            "const": "点"
          },
          "daily": {
            "$ref": "#/components/schemas/CompactIndexSeries"
          },
          "weekly": {
            "$ref": "#/components/schemas/CompactIndexSeries"
          },
          "monthly": {
            "$ref": "#/components/schemas/CompactIndexSeries"
          },
          "performance": {
            "type": "object",
            "properties": {
              "day_5": {
                "$ref": "#/components/schemas/CompactIndexScalar"
              },
              "day_20": {
                "$ref": "#/components/schemas/CompactIndexScalar"
              },
              "day_60": {
                "$ref": "#/components/schemas/CompactIndexScalar"
              },
              "year_1": {
                "$ref": "#/components/schemas/CompactIndexScalar"
              }
            },
            "required": [
              "day_5",
              "day_20",
              "day_60",
              "year_1"
            ],
            "additionalProperties": false
          },
          "definitions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": {
              "$ref": "#/components/schemas/CompactIndexDefinition"
            }
          }
        },
        "required": [
          "index_id",
          "snapshot_id",
          "formula_version",
          "calendar_version",
          "anchor_date",
          "pit_grade",
          "unit",
          "daily",
          "weekly",
          "monthly",
          "performance",
          "definitions"
        ],
        "additionalProperties": false
      },
      "CompactActivityCalculations": {
        "type": "object",
        "properties": {
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "price_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "market-activity-calculations-v1",
              "market-activity-calculations-sse-szse-v1"
            ]
          },
          "pit_grade": {
            "const": "latest_only",
            "type": "string"
          },
          "series": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "frequency": {
                  "type": "string",
                  "enum": [
                    "daily",
                    "weekly",
                    "monthly"
                  ]
                },
                "field": {
                  "type": "string",
                  "enum": [
                    "volume",
                    "amount"
                  ]
                },
                "rows": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "start": {
                        "type": "string",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                      },
                      "end": {
                        "type": "string",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                      },
                      "period_start": {
                        "type": "string",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                      },
                      "period_end": {
                        "type": "string",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                      },
                      "sample_count": {
                        "type": "integer"
                      },
                      "total": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "change_pct": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "ma": {
                        "type": "array",
                        "items": {
                          "$ref": "#/components/schemas/CompactActivityScalar"
                        }
                      }
                    },
                    "required": [
                      "start",
                      "end",
                      "period_start",
                      "period_end",
                      "sample_count",
                      "total",
                      "change_pct",
                      "ma"
                    ],
                    "additionalProperties": false
                  }
                },
                "ma_availability": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "period": {
                        "type": "integer"
                      },
                      "available": {
                        "type": "boolean"
                      },
                      "sample_count": {
                        "type": "integer"
                      },
                      "required_count": {
                        "type": "integer"
                      },
                      "reason": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      }
                    },
                    "required": [
                      "period",
                      "available",
                      "sample_count",
                      "required_count",
                      "reason"
                    ],
                    "additionalProperties": false
                  }
                }
              },
              "required": [
                "frequency",
                "field",
                "rows",
                "ma_availability"
              ],
              "additionalProperties": false
            }
          },
          "comparisons": {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "day_5": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  },
                  "day_20": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  },
                  "day_60": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  },
                  "year_1": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/CompactActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  }
                },
                "required": [
                  "day_5",
                  "day_20",
                  "day_60",
                  "year_1"
                ],
                "additionalProperties": false
              },
              {
                "type": "null"
              }
            ]
          },
          "definitions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": {
              "$ref": "#/components/schemas/CompactActivityDefinition"
            }
          }
        },
        "required": [
          "series_id",
          "activity_id",
          "price_snapshot_id",
          "formula_version",
          "pit_grade",
          "series",
          "comparisons",
          "definitions"
        ],
        "additionalProperties": false
      },
      "IndexSeriesCombinedView": {
        "type": "object",
        "properties": {
          "view": {
            "$ref": "#/components/schemas/IndexSeriesView"
          },
          "calculations": {
            "$ref": "#/components/schemas/CompactIndexCalculations"
          }
        },
        "required": [
          "view",
          "calculations"
        ],
        "additionalProperties": false
      },
      "MarketActivityCombinedView": {
        "type": "object",
        "properties": {
          "current": {
            "$ref": "#/components/schemas/MarketActivityCurrent"
          },
          "snapshot": {
            "$ref": "#/components/schemas/MarketActivitySnapshot"
          },
          "calculations": {
            "$ref": "#/components/schemas/CompactActivityCalculations"
          }
        },
        "required": [
          "current",
          "snapshot",
          "calculations"
        ],
        "additionalProperties": false
      },
      "IndexSeriesOverviewCalculations": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "formula_version": {
            "type": "string",
            "const": "index-price-calculations-v1"
          },
          "calendar_version": {
            "type": "string",
            "const": "cn-indices-sse-szse-2023-2026-v1"
          },
          "anchor_date": {
            "$ref": "#/components/schemas/Day"
          },
          "pit_grade": {
            "type": "string",
            "const": "latest_only"
          },
          "unit": {
            "type": "string",
            "const": "点"
          },
          "performance": {
            "type": "object",
            "properties": {
              "day_5": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              },
              "day_20": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              },
              "day_60": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              },
              "year_1": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              }
            },
            "required": [
              "day_5",
              "day_20",
              "day_60",
              "year_1"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "index_id",
          "snapshot_id",
          "formula_version",
          "calendar_version",
          "anchor_date",
          "pit_grade",
          "unit",
          "performance"
        ],
        "additionalProperties": false
      },
      "CompactIndexOverviewCalculations": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "formula_version": {
            "type": "string",
            "const": "index-price-calculations-v1"
          },
          "calendar_version": {
            "type": "string",
            "const": "cn-indices-sse-szse-2023-2026-v1"
          },
          "anchor_date": {
            "$ref": "#/components/schemas/Day"
          },
          "pit_grade": {
            "type": "string",
            "const": "latest_only"
          },
          "unit": {
            "type": "string",
            "const": "点"
          },
          "performance": {
            "type": "object",
            "properties": {
              "day_5": {
                "$ref": "#/components/schemas/CompactIndexScalar"
              },
              "day_20": {
                "$ref": "#/components/schemas/CompactIndexScalar"
              },
              "day_60": {
                "$ref": "#/components/schemas/CompactIndexScalar"
              },
              "year_1": {
                "$ref": "#/components/schemas/CompactIndexScalar"
              }
            },
            "required": [
              "day_5",
              "day_20",
              "day_60",
              "year_1"
            ],
            "additionalProperties": false
          },
          "definitions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": {
              "$ref": "#/components/schemas/CompactIndexDefinition"
            }
          }
        },
        "required": [
          "index_id",
          "snapshot_id",
          "formula_version",
          "calendar_version",
          "anchor_date",
          "pit_grade",
          "unit",
          "performance",
          "definitions"
        ],
        "additionalProperties": false
      },
      "IndexSeriesOverviewView": {
        "type": "object",
        "properties": {
          "view": {
            "$ref": "#/components/schemas/IndexSeriesView"
          },
          "calculations": {
            "$ref": "#/components/schemas/CompactIndexOverviewCalculations"
          }
        },
        "required": [
          "view",
          "calculations"
        ],
        "additionalProperties": false
      },
      "IndexSeriesViewResponse": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/IndexSeriesCombinedView"
          },
          {
            "$ref": "#/components/schemas/IndexSeriesOverviewView"
          }
        ]
      },
      "StoredDateRange": {
        "type": "object",
        "properties": {
          "start": {
            "$ref": "#/components/schemas/Day"
          },
          "end": {
            "$ref": "#/components/schemas/Day"
          }
        },
        "required": [
          "start",
          "end"
        ],
        "additionalProperties": false
      },
      "StoredVersion": {
        "type": "object",
        "properties": {
          "publication_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "observation_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "first_observation_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "source_coverage": {
            "$ref": "#/components/schemas/StoredDateRange"
          },
          "binding": {
            "type": "string"
          }
        },
        "required": [
          "publication_id",
          "observation_id",
          "first_observation_id",
          "source_coverage",
          "binding"
        ],
        "additionalProperties": false
      },
      "MarketVersions": {
        "type": "object",
        "properties": {
          "store_id": {
            "type": "string",
            "pattern": "^[0-9a-f]{32}$"
          },
          "indices": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "index_id": {
                  "$ref": "#/components/schemas/IndexSeriesId"
                },
                "price": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/StoredVersion"
                    },
                    {
                      "type": "null"
                    }
                  ]
                },
                "activity": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/StoredVersion"
                    },
                    {
                      "type": "null"
                    }
                  ]
                }
              },
              "required": [
                "index_id",
                "price",
                "activity"
              ],
              "additionalProperties": false
            }
          },
          "markets": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "series_id": {
                  "$ref": "#/components/schemas/MarketActivitySeriesId"
                },
                "activity": {
                  "anyOf": [
                    {
                      "$ref": "#/components/schemas/StoredVersion"
                    },
                    {
                      "type": "null"
                    }
                  ]
                }
              },
              "required": [
                "series_id",
                "activity"
              ],
              "additionalProperties": false
            }
          },
          "etf": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/StoredVersion"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "store_id",
          "indices",
          "markets",
          "etf"
        ],
        "additionalProperties": false
      },
      "StorageStatus": {
        "type": "object",
        "properties": {
          "quarantined": {
            "type": "boolean"
          },
          "reason": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "last_structure": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "last_full": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "structure_due": {
            "type": "boolean"
          },
          "full_due": {
            "type": "boolean"
          },
          "available": {
            "type": "boolean"
          }
        },
        "required": [
          "quarantined",
          "reason",
          "last_structure",
          "last_full",
          "structure_due",
          "full_due",
          "available"
        ],
        "additionalProperties": false
      },
      "StoredPriceOverview": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "formula_version": {
            "type": "string",
            "const": "index-price-calculations-v1"
          },
          "calendar_version": {
            "type": "string",
            "const": "cn-indices-sse-szse-2023-2026-v1"
          },
          "anchor_date": {
            "$ref": "#/components/schemas/Day"
          },
          "pit_grade": {
            "type": "string",
            "const": "latest_only"
          },
          "unit": {
            "type": "string",
            "const": "点"
          },
          "storage_decimals": {
            "type": "integer",
            "enum": [
              2,
              4
            ]
          },
          "verification": {
            "$ref": "#/components/schemas/IndexSeriesVerification"
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "source_coverage": {
            "$ref": "#/components/schemas/StoredDateRange"
          },
          "requested_range": {
            "$ref": "#/components/schemas/StoredDateRange"
          },
          "returned_range": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/StoredDateRange"
              },
              {
                "type": "null"
              }
            ]
          },
          "calculation_input_range": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/StoredDateRange"
              },
              {
                "type": "null"
              }
            ]
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesRetrievalSource"
            }
          },
          "instrument": {
            "$ref": "#/components/schemas/IndexSeriesInstrument"
          },
          "source_policy_version": {
            "$ref": "#/components/schemas/IndexSeriesSourcePolicy"
          },
          "summary": {
            "$ref": "#/components/schemas/IndexSeriesSummary"
          },
          "performance": {
            "type": "object",
            "properties": {
              "day_5": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              },
              "day_20": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              },
              "day_60": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              },
              "year_1": {
                "$ref": "#/components/schemas/IndexSeriesCalculationScalar"
              }
            },
            "required": [
              "day_5",
              "day_20",
              "day_60",
              "year_1"
            ],
            "additionalProperties": false
          },
          "observed_at": {
            "type": "string"
          },
          "bars": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "trade_date": {
                  "$ref": "#/components/schemas/Day"
                },
                "open": {
                  "$ref": "#/components/schemas/IndexSeriesPoint"
                },
                "high": {
                  "$ref": "#/components/schemas/IndexSeriesPoint"
                },
                "low": {
                  "$ref": "#/components/schemas/IndexSeriesPoint"
                },
                "close": {
                  "$ref": "#/components/schemas/IndexSeriesPoint"
                }
              },
              "required": [
                "trade_date",
                "open",
                "high",
                "low",
                "close"
              ],
              "additionalProperties": false
            }
          }
        },
        "required": [
          "index_id",
          "snapshot_id",
          "formula_version",
          "calendar_version",
          "anchor_date",
          "pit_grade",
          "unit",
          "storage_decimals",
          "verification",
          "observation_id",
          "source_coverage",
          "requested_range",
          "returned_range",
          "calculation_input_range",
          "sources",
          "instrument",
          "source_policy_version",
          "summary",
          "performance",
          "observed_at",
          "bars"
        ],
        "additionalProperties": false
      },
      "StoredPriceRange": {
        "type": "object",
        "properties": {
          "index_id": {
            "$ref": "#/components/schemas/IndexSeriesId"
          },
          "snapshot_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "formula_version": {
            "type": "string",
            "const": "index-price-calculations-v1"
          },
          "calendar_version": {
            "type": "string",
            "const": "cn-indices-sse-szse-2023-2026-v1"
          },
          "anchor_date": {
            "$ref": "#/components/schemas/Day"
          },
          "pit_grade": {
            "type": "string",
            "const": "latest_only"
          },
          "unit": {
            "type": "string",
            "const": "点"
          },
          "storage_decimals": {
            "type": "integer",
            "enum": [
              2,
              4
            ]
          },
          "verification": {
            "$ref": "#/components/schemas/IndexSeriesVerification"
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "source_coverage": {
            "$ref": "#/components/schemas/StoredDateRange"
          },
          "requested_range": {
            "$ref": "#/components/schemas/StoredDateRange"
          },
          "returned_range": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/StoredDateRange"
              },
              {
                "type": "null"
              }
            ]
          },
          "calculation_input_range": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/StoredDateRange"
              },
              {
                "type": "null"
              }
            ]
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/IndexSeriesRetrievalSource"
            }
          },
          "frequency": {
            "type": "string",
            "enum": [
              "daily",
              "weekly",
              "monthly"
            ]
          },
          "ma_periods": {
            "type": "array",
            "maxItems": 8,
            "items": {
              "type": "integer",
              "enum": [
                5,
                10,
                20,
                30,
                60,
                120,
                180,
                250
              ]
            }
          },
          "series": {
            "$ref": "#/components/schemas/IndexSeriesCalculationSeries"
          },
          "navigation_periods": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1100,
            "items": {
              "$ref": "#/components/schemas/StoredDateRange"
            },
            "description": "固定发布全覆盖的实际周期起止日，仅日期导航，不含范围外行情值。"
          }
        },
        "required": [
          "index_id",
          "snapshot_id",
          "formula_version",
          "calendar_version",
          "anchor_date",
          "pit_grade",
          "unit",
          "storage_decimals",
          "verification",
          "observation_id",
          "source_coverage",
          "requested_range",
          "returned_range",
          "calculation_input_range",
          "sources",
          "frequency",
          "ma_periods",
          "series",
          "navigation_periods"
        ],
        "additionalProperties": false
      },
      "StoredPriceView": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/StoredPriceOverview"
          },
          {
            "$ref": "#/components/schemas/StoredPriceRange"
          }
        ]
      },
      "StoredActivitySeries": {
        "type": "object",
        "properties": {
          "frequency": {
            "type": "string",
            "enum": [
              "daily",
              "weekly",
              "monthly"
            ]
          },
          "field": {
            "type": "string",
            "enum": [
              "volume",
              "amount"
            ]
          },
          "rows": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "start": {
                  "type": "string",
                  "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                },
                "end": {
                  "type": "string",
                  "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                },
                "period_start": {
                  "type": "string",
                  "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                },
                "period_end": {
                  "type": "string",
                  "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                },
                "sample_count": {
                  "type": "integer"
                },
                "total": {
                  "$ref": "#/components/schemas/MarketActivityScalar"
                },
                "change_pct": {
                  "$ref": "#/components/schemas/MarketActivityScalar"
                },
                "ma": {
                  "type": "array",
                  "items": {
                    "$ref": "#/components/schemas/MarketActivityScalar"
                  }
                }
              },
              "required": [
                "start",
                "end",
                "period_start",
                "period_end",
                "sample_count",
                "total",
                "change_pct",
                "ma"
              ],
              "additionalProperties": false
            }
          },
          "ma_availability": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "period": {
                  "type": "integer"
                },
                "available": {
                  "type": "boolean"
                },
                "sample_count": {
                  "type": "integer"
                },
                "required_count": {
                  "type": "integer"
                },
                "reason": {
                  "anyOf": [
                    {
                      "type": "string"
                    },
                    {
                      "type": "null"
                    }
                  ]
                }
              },
              "required": [
                "period",
                "available",
                "sample_count",
                "required_count",
                "reason"
              ],
              "additionalProperties": false
            }
          }
        },
        "required": [
          "frequency",
          "field",
          "rows",
          "ma_availability"
        ],
        "additionalProperties": false
      },
      "StoredActivityRange": {
        "type": "object",
        "properties": {
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "price_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "market-activity-calculations-v1",
              "market-activity-calculations-sse-szse-v1"
            ]
          },
          "pit_grade": {
            "const": "latest_only",
            "type": "string"
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "anchor_date": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "calendar_version": {
            "type": "string"
          },
          "source_policy_version": {
            "type": "string"
          },
          "source_coverage": {
            "$ref": "#/components/schemas/StoredDateRange"
          },
          "requested_range": {
            "$ref": "#/components/schemas/StoredDateRange"
          },
          "returned_range": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/StoredDateRange"
              },
              {
                "type": "null"
              }
            ]
          },
          "calculation_input_range": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/StoredDateRange"
              },
              {
                "type": "null"
              }
            ]
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/MarketActivityObservedSource"
            }
          },
          "frequency": {
            "type": "string",
            "enum": [
              "daily",
              "weekly",
              "monthly"
            ]
          },
          "ma_periods": {
            "type": "array",
            "maxItems": 8,
            "items": {
              "type": "integer",
              "enum": [
                5,
                10,
                20,
                30,
                60,
                120,
                180,
                250
              ]
            }
          },
          "field": {
            "type": "string",
            "enum": [
              "volume",
              "amount"
            ]
          },
          "series": {
            "$ref": "#/components/schemas/StoredActivitySeries"
          },
          "source_scope": {
            "type": "string"
          },
          "source_revision_relation": {
            "const": "unknown",
            "type": "string"
          },
          "binding": {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "version": {
                    "type": "string"
                  },
                  "price_object_id": {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  "activity_object_id": {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  "relation": {
                    "type": "string",
                    "enum": [
                      "same_source_object",
                      "different_source_objects"
                    ]
                  },
                  "comparison": {
                    "const": "exact_available_values_match",
                    "type": "string"
                  }
                },
                "required": [
                  "version",
                  "price_object_id",
                  "activity_object_id",
                  "relation",
                  "comparison"
                ],
                "additionalProperties": false
              },
              {
                "type": "null"
              }
            ]
          },
          "navigation_periods": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1100,
            "items": {
              "$ref": "#/components/schemas/StoredDateRange"
            },
            "description": "固定发布全覆盖的实际周期起止日，仅日期导航，不含范围外行情值。"
          }
        },
        "required": [
          "series_id",
          "activity_id",
          "price_snapshot_id",
          "formula_version",
          "pit_grade",
          "observation_id",
          "anchor_date",
          "calendar_version",
          "source_policy_version",
          "source_coverage",
          "requested_range",
          "returned_range",
          "calculation_input_range",
          "sources",
          "frequency",
          "ma_periods",
          "field",
          "series",
          "source_scope",
          "source_revision_relation",
          "binding",
          "navigation_periods"
        ],
        "additionalProperties": false
      },
      "StoredMarketOverview": {
        "type": "object",
        "properties": {
          "series_id": {
            "type": "string",
            "enum": [
              "sse:000001:price",
              "szse:399001:price",
              "szse:399006:price",
              "sse:000688:price",
              "cn-a-turnover",
              "cn-a-turnover-sse-szse"
            ]
          },
          "activity_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "price_snapshot_id": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ObjectId"
              },
              {
                "type": "null"
              }
            ]
          },
          "formula_version": {
            "type": "string",
            "enum": [
              "market-activity-calculations-v1",
              "market-activity-calculations-sse-szse-v1"
            ]
          },
          "pit_grade": {
            "const": "latest_only",
            "type": "string"
          },
          "observation_id": {
            "$ref": "#/components/schemas/ObjectId"
          },
          "anchor_date": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "calendar_version": {
            "type": "string"
          },
          "source_policy_version": {
            "type": "string"
          },
          "source_coverage": {
            "$ref": "#/components/schemas/StoredDateRange"
          },
          "requested_range": {
            "$ref": "#/components/schemas/StoredDateRange"
          },
          "returned_range": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/StoredDateRange"
              },
              {
                "type": "null"
              }
            ]
          },
          "calculation_input_range": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/StoredDateRange"
              },
              {
                "type": "null"
              }
            ]
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/MarketActivityObservedSource"
            }
          },
          "series": {
            "$ref": "#/components/schemas/StoredActivitySeries"
          },
          "comparisons": {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "day_5": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  },
                  "day_20": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  },
                  "day_60": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  },
                  "year_1": {
                    "type": "object",
                    "properties": {
                      "baseline": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "comparison": {
                        "$ref": "#/components/schemas/MarketActivityScalar"
                      },
                      "sample_count": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "baseline",
                      "comparison",
                      "sample_count"
                    ],
                    "additionalProperties": false
                  }
                },
                "required": [
                  "day_5",
                  "day_20",
                  "day_60",
                  "year_1"
                ],
                "additionalProperties": false
              },
              {
                "type": "null"
              }
            ]
          },
          "source_scope": {
            "type": "string"
          },
          "source_revision_relation": {
            "const": "unknown",
            "type": "string"
          },
          "binding": {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "version": {
                    "type": "string"
                  },
                  "price_object_id": {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  "activity_object_id": {
                    "$ref": "#/components/schemas/ObjectId"
                  },
                  "relation": {
                    "type": "string",
                    "enum": [
                      "same_source_object",
                      "different_source_objects"
                    ]
                  },
                  "comparison": {
                    "const": "exact_available_values_match",
                    "type": "string"
                  }
                },
                "required": [
                  "version",
                  "price_object_id",
                  "activity_object_id",
                  "relation",
                  "comparison"
                ],
                "additionalProperties": false
              },
              {
                "type": "null"
              }
            ]
          },
          "navigation_periods": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1100,
            "items": {
              "$ref": "#/components/schemas/StoredDateRange"
            },
            "description": "固定发布全覆盖的实际周期起止日，仅日期导航，不含范围外行情值。"
          }
        },
        "required": [
          "series_id",
          "activity_id",
          "price_snapshot_id",
          "formula_version",
          "pit_grade",
          "observation_id",
          "anchor_date",
          "calendar_version",
          "source_policy_version",
          "source_coverage",
          "requested_range",
          "returned_range",
          "calculation_input_range",
          "sources",
          "series",
          "comparisons",
          "source_scope",
          "source_revision_relation",
          "binding",
          "navigation_periods"
        ],
        "additionalProperties": false
      },
      "StoredActivityView": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/StoredActivityRange"
          },
          {
            "$ref": "#/components/schemas/StoredMarketOverview"
          }
        ]
      }
    },
    "parameters": {
      "ClientMarker": {
        "name": "X-Wolf-Client",
        "in": "header",
        "required": true,
        "schema": {
          "type": "string",
          "const": "1"
        }
      },
      "ExpectedInstance": {
        "name": "X-Wolf-Expected-Instance",
        "in": "header",
        "required": true,
        "schema": {
          "$ref": "#/components/schemas/PublicInstanceId"
        }
      },
      "ExpectedConfig": {
        "name": "X-Wolf-Expected-Config",
        "in": "header",
        "required": true,
        "schema": {
          "$ref": "#/components/schemas/PublicDigest"
        }
      },
      "RequestId": {
        "name": "X-Wolf-Request-Id",
        "in": "header",
        "required": true,
        "schema": {
          "$ref": "#/components/schemas/RequestId"
        }
      }
    },
    "headers": {
      "ResponseInstance": {
        "schema": {
          "$ref": "#/components/schemas/PublicInstanceId"
        },
        "description": "Actual serving process; required after successful binding, including business errors."
      },
      "ResponseConfig": {
        "schema": {
          "$ref": "#/components/schemas/PublicDigest"
        },
        "description": "Frozen serving config; required after successful binding, including business errors."
      },
      "NoStore": {
        "schema": {
          "type": "string",
          "const": "no-store"
        }
      }
    }
  },
  "security": [],
  "x-wolf-disabled-routes": {
    "/api/demo/research": [
      "get"
    ],
    "/api/documents/{document_id}/evidence": [
      "get"
    ],
    "/openapi.json": [
      "get",
      "head"
    ],
    "/docs": [
      "get",
      "head"
    ],
    "/docs/oauth2-redirect": [
      "get",
      "head"
    ],
    "/redoc": [
      "get",
      "head"
    ],
    "/api/indices/000300/snapshots/{snapshot_id}": [
      "get",
      "options"
    ],
    "/api/indices/000300/update": [
      "get",
      "post",
      "options"
    ],
    "/api/snapshots/{snapshot_id}/pdf/{object_id}": [
      "get",
      "options"
    ],
    "/api/indices/000300": [
      "get",
      "options"
    ],
    "/api/indices/000300/snapshots/{snapshot_id}/evidence/{object_id}": [
      "get",
      "options"
    ],
    "/api/slice": [
      "get",
      "options"
    ],
    "/api/snapshots/{snapshot_id}": [
      "get",
      "options"
    ],
    "/api/slice/update": [
      "get",
      "post",
      "options"
    ],
    "/api/operations/{request_id}": [
      "get",
      "options"
    ]
  },
  "x-wolf-transport": {
    "bind": "127.0.0.1 only; one worker; no reload/fork workers",
    "host": "Exactly one raw Host, exact configured 127.0.0.1:port. No localhost, IPv6, trailing dot, credentials or forwarded-host substitution. Proxy validates its own exact inbound authority and rewrites outbound Host only to its fixed backend authority.",
    "single_headers": [
      "Host",
      "Origin",
      "X-Wolf-Client",
      "X-Wolf-Expected-Instance",
      "X-Wolf-Expected-Config",
      "X-Wolf-Request-Id",
      "Content-Type",
      "Access-Control-Request-Method",
      "Access-Control-Request-Headers"
    ],
    "duplicate_headers": "Reject duplicate raw header fields before joining/coercion (case insensitive names), including identical duplicates. Reject comma-joined singleton values and control/non-ASCII values. Exception: the single raw Access-Control-Request-Headers field is a comma-delimited set per preflight; normal multiple members are allowed, duplicate or unpermitted members rejected. HTTP parser rejections/connection-close occur before app and need raw transport evidence; no promise of JSON for parser failures.",
    "origin": "Present Origin must be one exact configured entry; empty, null, wildcard, suffix match and unknown denied. This browser-read profile accepts only explicit http://127.0.0.1:port browser origins. Native schemes and implicit localhost:1420 are not enabled.",
    "fetch_metadata": "Without Origin reject Sec-Fetch-Site cross-site or same-site. With exact allowed Origin permit cross-site for explicitly allowed host pair; absent metadata is not proof of trust. Reject unknown/malformed metadata. Navigation mode or document/iframe/frame destination denied on actual API calls. Preflight evaluates Origin/method/headers only after Host.",
    "actual": "Host then Origin/Fetch Metadata then marker, route/method, input/media/write switch, then bound context, then operation reservation/business I/O. Missing context ->400 connection_context_required; malformed ->400 connection_context_invalid; unequal frozen instance/config ->409 connection_context_mismatch. Missing marker ->403 client_marker_required.",
    "post": "Allowed nonmissing Origin; application/json optionally charset=utf-8; exact empty object; required request_id and bound context. Other media ->415; malformed JSON/invalid input ->422 invalid_request; no automatic retry. Extra JSON fields denied; unknown/duplicate query fields denied on every operation.",
    "preflight": "Only known active path and supported advertised method. Require singleton Origin, requested method and requested-headers set including x-wolf-client, bound context names for business routes and request-id/content-type for writes. Set must be subset of allowed headers; order/case irrelevant, repeated names denied. No actual marker/context values, no writeswitch/context comparison or business I/O. Missing/invalid metadata400; denied Origin403; unknown path404; unsupported advertised method405.",
    "cors": {
      "allow_credentials": false,
      "allow_origin": "echo exact allowed Origin only",
      "vary_actual": "Origin",
      "allowed_headers": [
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "X-Wolf-Client",
        "X-Wolf-Expected-Instance",
        "X-Wolf-Expected-Config",
        "X-Wolf-Request-Id"
      ],
      "expose_headers": [
        "X-Wolf-Instance",
        "X-Wolf-Config"
      ],
      "error_headers": "For an allowed Origin, all app responses including 4xx/500 carry CORS and Vary. Denied Origin gets no ACAO. Proxy neither invents Origin nor marker; reject/strip untrusted forwarding semantics."
    },
    "fallback": "After global Host/Origin/metadata/marker guards: disabled/unknown route404 route_not_found; known route unsupported method405 method_not_allowed plus Allow containing its explicit methods and OPTIONS. No API HEAD supported in target; HEAD error has no body, its GET-equivalent error status/headers only. OPTIONS uses separate preflight guards and never requires actual marker. TRACE/CONNECT denied, no redirect or slash normalization creating bypass. Raw parser failures separately recorded.",
    "fallback_responses": {
      "400": {
        "description": "Global fallback response",
        "content": {
          "application/json": {
            "schema": {
              "$ref": "#/components/schemas/BoundaryError400"
            }
          }
        }
      },
      "403": {
        "description": "Global fallback response",
        "content": {
          "application/json": {
            "schema": {
              "$ref": "#/components/schemas/BoundaryError403"
            }
          }
        }
      },
      "404": {
        "description": "Global fallback response",
        "content": {
          "application/json": {
            "schema": {
              "$ref": "#/components/schemas/BoundaryError404"
            }
          }
        }
      },
      "405": {
        "description": "Global fallback response",
        "content": {
          "application/json": {
            "schema": {
              "$ref": "#/components/schemas/BoundaryError405"
            }
          }
        }
      }
    },
    "cache": "All non-preflight API responses Cache-Control:no-store; no cache reuse across process/config. No redirect following by Client or proxy.",
    "health": "Public non-business diagnostic with common marker/Host/Origin guards; no context binding, no data-root probe. Storage field identifies configured backend kind, not disk readiness.",
    "html": "C1-02 actual HTML provider: enforced CSP frame-ancestors none (quoted none in header) and X-Frame-Options DENY on home, direct route and SPA fallback, both development/daily and final proxy response. This API contract does not generate or verify HTML headers."
  },
  "x-wolf-operation-semantics": {
    "capacity": 4096,
    "retention": "All association rows including final/rejected retained until process exit; no eviction. Existing identity lookup occurs before new-capacity check; new full request503 before business I/O. Reserve under process mutex after all guards and before acquiring business locks.",
    "key": [
      "instance_id",
      "config_id",
      "request_id",
      "operation"
    ],
    "uniqueness": "Within instance/config, reusing request_id for different operation or canonical body ->409 request_id_conflict, no second business call. Identical duplicate waits for original admission to settle or transport times out; it never repeats execution. Process mutex/row event released before background work.",
    "acceptance": "Associate the actual index-series job and save its admission result before background handoff. Busy/conflicting requests retain existing rejection semantics. Update terminal state only from the exact linked job.",
    "post_replay": "Return saved initial status/body including recorded business rejection. Prior request not definitively associated after internal failure remains unknown; do not rerun it. Request IDs are not idempotency across process restart.",
    "lookup": "GET lookup is itself bound to current process; query fields name the original identity. Different original instance/config, missing/incomplete row ->200 state unknown. This is not proof of nonexecution. No business DB lookup for this endpoint.",
    "state_constraints": "Operation kind chooses matching business_status schema; job_id must equal status.job_id. accepted/running require nonnull job/reused_job/status and null rejection; completed/failed/interrupted require exact job terminal status and null rejection; rejected requires nonnull rejection, null job/status/reused_job; unknown has null status/rejection and nullable known job/reused_job. All combinations require explicit semantic tests.",
    "client": "Persist public unknown identity before dispatch; cancellation is not server cancellation; poll lookup read only, never repeat POST. After refresh/reconnect/new instance keep uncertainty and separate latest business status."
  },
  "x-wolf-stage": {
    "identity": "SQLITE-MIGRATION-20261108",
    "state": "market-overview-baseline",
    "contract_digest_rule": "SHA256 of exact UTF-8 active contract file bytes; not embedded inside this file. Expected descriptor and server packaged resource use identical bytes. Artifact filename extension is irrelevant; any reserialization changes digest and requires re-fixing.",
    "stage_profile": "统一SQLite、固定版本按需读取；保留旧数据，采集与周期更新须显式授权。"
  },
  "x-wolf-etf-operation-semantics": {
    "scope": "ETF logical domain in the shared SQLite store; preserved historical operation identities",
    "replay": "After current transport/config/write guards, look up the original request before new plan/CAS/budget checks. Same terminal200, same live202, changed parameters409.",
    "recovery": "Explicit identical POST only; one shared writer task across ETF and coordinator. Only the unique scoped zero-request ETF lease may finish; preserve counters and other batches.",
    "time": "Fixed selection_at, effective configuration, admission proofs and immutable original records. First backfill never creates historical published signals.",
    "client": "Store original config/instance/request/plan/expected snapshot before POST. Distinguish current serving config/instance; never retry POST automatically."
  }
}
