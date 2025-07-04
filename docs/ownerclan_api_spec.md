# 📎 오너클랜(Ownerclan) API 명세서

---

## 🔗 기본 정보

- **API 명**: 오너클랜 상품/판매사/주문 API
- **공급사명**: 오너클랜 (Ownerclan)
- **API 방식**: GraphQL
- **인증 방식**: JWT 기반 로그인 인증

---

## 🔐 인증 정보

### ✅ 인증 방식

- JWT 토큰 기반 인증 (1개월간 유효)
- 인증시 필요한 정보:
  - `service`: "ownerclan"
  - `userType`: "seller"
  - `username`: 판매사 ID
  - `password`: 판매사 PW

### 🔧 인증 엔드포인트

| 환경         | URL                                                                |
| ---------- | ------------------------------------------------------------------ |
| Production | [https://auth.ownerclan.com/auth](https://auth.ownerclan.com/auth) |

### 🔁 요청 방식 (JavaScript 예시)

```javascript
var authData = {
    service: "ownerclan",
    userType: "seller",
    username: "사용자ID",
    password: "사용자PW"
};

$.ajax({
    url: "https://auth.ownerclan.com/auth",
    type: "POST",
    contentType: "application/json",
    processData: false,
    data: JSON.stringify(authData),
    success: function(data) {
        console.log(data); // 토큰 발급 (텍스트 형태)
    },
    error: function(data) {
        console.error(data.responseText, data.status);
    }
});
```

> 유저점: 오너클랜은 **JSON 이 아니라 텍스트 형태**로 토큰을 반환하무로, 관리에 주의.

---

## 🌐 GraphQL API

### 포인트 엔드포인트

| 환경         | URL                                                                          |
| ---------- | ---------------------------------------------------------------------------- |
| Production | [https://api.ownerclan.com/v1/graphql](https://api.ownerclan.com/v1/graphql) |

### 🧪 GraphQL Playground

- 위 URL에서 GraphQL Playground 통해 테스트 가능

---

## 📦 상품 관련 그래프클 요청

### 📌 단일 상품 조회

```graphql
query {
  item(key: "ITEM000000") {
    key
    name
    model
    production
    origin
    price
    fixedPrice
    category { name }
    shippingFee
    shippingType
    status
    options {
      price
      quantity
      optionAttributes {
        name
        value
      }
    }
    taxFree
    adultOnly
    returnable
    images
    createdAt
    updatedAt
  }
}
```

### 📌 보수 상품 조회 (Pagination)

```graphql
query {
  allItems(first: 100, after: "<cursor>") {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        key
        name
        price
        status
      }
    }
  }
}
```

### 📌 보수 상품 조회 (Key 리스트)

```graphql
query {
  items(keys: ["ITEM001", "ITEM002"]) {
    key
    name
    model
    price
    status
    images
  }
}
```

### 📌 상품 변경 이력 조회

```graphql
query {
  itemHistories(first: 100, dateFrom: 1690000000, kind: OUT_OF_STOCK, itemKey: "ITEM001") {
    edges {
      node {
        createdAt
        kind
        itemKey
      }
    }
  }
}
```

---

## 📎 주문 관련 그래프클 요청

### 📌 단일 주문 조회

```graphql
query {
  order(key: "2020000000000000000A") {
    key
    id
    products {
      quantity
      price
      itemKey
    }
    status
    shippingInfo {
      recipient {
        name
        destinationAddress {
          addr1
          addr2
          postalCode
        }
      }
    }
    createdAt
    updatedAt
  }
}
```

### 📌 보수 주문 조회

```graphql
query {
  allOrders(first: 100, after: "<cursor>", dateFrom: 1690000000, dateTo: 1699999999) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      cursor
      node {
        key
        status
        createdAt
      }
    }
  }
}
```

### 📌 주문 등록

```graphql
mutation {
  createOrder(input: {
    sender: {...},
    recipient: {...},
    products: [...],
    note: "메모"
  }) {
    key
    status
    createdAt
  }
}
```

### 📌 주문 시뮬레이션

```graphql
query {
  simulateCreateOrder(input: {...}) {
    itemAmounts {
      amount
      itemKey
    }
    shippingAmount
  }
}
```

### 📌 주문 메모 업데이트

```graphql
mutation {
  updateOrderNotes(key: "2020000000000000000A", input: {
    note: "메모 업데이트",
    sellerNotes: [{ sellerNote: "개별 메모" }]
  }) {
    key
    note
    sellerNote
  }
}
```

### 📌 주문 취소

```graphql
mutation CancelOrder($key: ID!) {
  cancelOrder(key: $key) {
    key
    status
    updatedAt
  }
}
```

### 📌 주문 취소 요청

```graphql
mutation RequestOrderCancellation($key: ID!, $input: RequestOrderCancellationInput!) {
  requestOrderCancellation(key: $key, input: $input) {
    key
    status
    updatedAt
  }
}
```

---

## 📂 카테고리 관련 요청

### 📌 단일 카테고리 조회

```graphql
query {
  category(key: "00000000") {
    key
    name
    fullName
    attributes
    parent { key name }
    children { key name }
    ancestors { key name }
    descendants(first: 100) {
      edges {
        node { key name }
      }
    }
  }
}
```

---

## 🖊️ 기타 정보

- 모든 API 요청은 JWT 토큰 유지 상태에서야 정상 동작
- GraphQL 요청은 필드 선택 가능 (선택적 쿼리)
- GraphQL Playground에서 실시간 테스트 권장
- 인증 토큰은 반드시 `.env` 등에 보안 저장

> 이 문서는 오너클랜 API 연동을 위한 명세 정보입니다. fetcher/parser 모듈 개발 까지 여부 가능한 값을 가지고 있습니다.

