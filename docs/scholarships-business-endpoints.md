# Scholarships Module - Đặc tả nghiệp vụ chi tiết

## 1. Mục tiêu tài liệu

Tài liệu này mô tả chi tiết luồng nghiệp vụ học bổng từ đầu đến cuối:

1. Học bổng được tạo như thế nào, cần thông tin gì, ý nghĩa từng nhóm thông tin.
2. Sinh viên đăng ký ra sao, dữ liệu nào bắt buộc, dữ liệu đó nằm ở bảng/trường nào.
3. Trạng thái hồ sơ đăng ký và các quy tắc chuyển trạng thái.
4. Quy trình review tác động lên bảng nào, cập nhật trường nào.
5. Sinh viên kiểm tra kết quả bằng cách nào để biết đậu/rớt.

## 2. Vai trò trong hệ thống

1. Quản trị viên hoặc vận hành học bổng
   Thực hiện tạo danh mục, tạo học bổng, định nghĩa yêu cầu và giấy tờ.
2. Sinh viên
   Tạo hồ sơ đăng ký, upload giấy tờ, submit hồ sơ, theo dõi kết quả.
3. Reviewer hoặc hội đồng duyệt
   Review theo từng giai đoạn, duyệt giấy tờ, đưa ra quyết định cuối cùng.

## 3. Mô hình dữ liệu cốt lõi

## 3.1 Bảng scholarships (chương trình học bổng)

Một bản ghi trong bảng này đại diện cho một chương trình học bổng cụ thể.

Nhóm trường chính:

1. Định danh và mô tả

- id
- name
- description
- image

2. Điều kiện và quyền lợi

- eligibility_criteria
- benefits

3. Giá trị học bổng

- amount
- currency
- quantity

4. Thời gian

- application_deadline
- result_announcement_date

5. Đơn vị cấp và phân loại

- category_id
- provider_id
- provider

6. Thông tin liên hệ

- contact_email
- contact_phone
- official_website

7. Trạng thái hiển thị

- is_active

## 3.2 Bảng scholarship_categories (danh mục học bổng)

Mỗi danh mục là một nhóm phân loại như: Merit, Need-based, Research.

Trường chính:

- id
- name
- description

## 3.3 Bảng scholarship_requirements (yêu cầu hồ sơ)

Mỗi bản ghi là một yêu cầu nghiệp vụ của học bổng.

Trường chính:

- scholarship_id
- title
- description
- is_required
- sort_order

Ý nghĩa:

- Đây là điều kiện để hướng dẫn sinh viên chuẩn bị hồ sơ đúng chuẩn.

## 3.4 Bảng scholarship_documents (giấy tờ cần nộp)

Mỗi bản ghi là một loại tài liệu sinh viên cần nộp cho học bổng.

Trường chính:

- scholarship_id
- document_name
- document_type
- is_required
- max_file_size_mb
- sample_url

Ý nghĩa:

- Đây là bộ checklist giấy tờ cho từng học bổng.

## 3.5 Bảng student_scholarships (hồ sơ ứng tuyển của sinh viên)

Mỗi bản ghi là một hồ sơ đăng ký học bổng của một sinh viên.

Trường chính:

- user_id
- scholarship_id
- status
- application_date
- submitted_form_url
- note
- feedback
- reviewer_id
- decision_date
- awarded_amount
- currency

Ý nghĩa:

- Đây là bảng trung tâm thể hiện tình trạng đậu/rớt và tiến trình xét duyệt.

## 3.6 Bảng student_scholarship_documents (tài liệu sinh viên đã nộp)

Mỗi bản ghi là một file cụ thể mà sinh viên nộp cho một hồ sơ.

Trường chính:

- student_scholarship_id
- document_id
- file_url
- upload_date
- status
- reviewer_note

## 3.7 Bảng scholarship_reviews (nhật ký review theo giai đoạn)

Mỗi bản ghi là một lần review tại một stage của hồ sơ.

Trường chính:

- student_scholarship_id
- reviewer_id
- stage
- status
- comment
- reviewed_at

## 3.8 Danh sách bảng và cột dữ liệu (DB real)

Phần này liệt kê theo schema thực tế trong migration của module scholarship.

## 3.8.1 scholarship_categories

Mục đích:

- Danh mục phân loại học bổng.

| Cột DB      | Kiểu dữ liệu | Null | Mặc định           | Ràng buộc |
| ----------- | ------------ | ---- | ------------------ | --------- |
| id          | uuid         | No   | uuid_generate_v4() | PK        |
| name        | varchar(255) | No   | -                  | UNIQUE    |
| description | text         | Yes  | -                  | -         |
| created_at  | timestamp    | No   | now()              | -         |
| updated_at  | timestamp    | No   | now()              | -         |

## 3.8.2 scholarships

Mục đích:

- Lưu thông tin chương trình học bổng để hiển thị, lọc và mở đăng ký.

| Cột DB                   | Kiểu dữ liệu  | Null | Mặc định           | Ràng buộc                       |
| ------------------------ | ------------- | ---- | ------------------ | ------------------------------- |
| id                       | uuid          | No   | uuid_generate_v4() | PK                              |
| name                     | varchar(255)  | No   | -                  | -                               |
| description              | text          | Yes  | -                  | -                               |
| eligibility_criteria     | text          | Yes  | -                  | -                               |
| provider                 | varchar(255)  | Yes  | -                  | -                               |
| amount                   | numeric(15,2) | Yes  | -                  | -                               |
| currency                 | varchar(3)    | Yes  | -                  | -                               |
| quantity                 | integer       | Yes  | -                  | -                               |
| application_deadline     | timestamp     | Yes  | -                  | -                               |
| result_announcement_date | timestamp     | Yes  | -                  | -                               |
| benefits                 | text          | Yes  | -                  | -                               |
| contact_email            | varchar(255)  | Yes  | -                  | -                               |
| contact_phone            | varchar(50)   | Yes  | -                  | -                               |
| official_website         | varchar(500)  | Yes  | -                  | -                               |
| image                    | varchar(500)  | Yes  | -                  | -                               |
| category_id              | uuid          | Yes  | -                  | FK -> scholarship_categories.id |
| provider_id              | uuid          | Yes  | -                  | FK -> organizations.id          |
| is_active                | boolean       | No   | true               | -                               |
| created_at               | timestamp     | No   | now()              | -                               |
| updated_at               | timestamp     | No   | now()              | -                               |

## 3.8.3 scholarship_requirements

Mục đích:

- Lưu các điều kiện hoặc checklist yêu cầu cho từng học bổng.

| Cột DB         | Kiểu dữ liệu | Null | Mặc định           | Ràng buộc             |
| -------------- | ------------ | ---- | ------------------ | --------------------- |
| id             | uuid         | No   | uuid_generate_v4() | PK                    |
| scholarship_id | uuid         | No   | -                  | FK -> scholarships.id |
| title          | varchar(255) | No   | -                  | -                     |
| description    | text         | Yes  | -                  | -                     |
| is_required    | boolean      | No   | false              | -                     |
| sort_order     | integer      | No   | 0                  | -                     |
| created_at     | timestamp    | No   | now()              | -                     |
| updated_at     | timestamp    | No   | now()              | -                     |

## 3.8.4 scholarship_documents

Mục đích:

- Định nghĩa các loại giấy tờ cần nộp cho từng học bổng.

| Cột DB           | Kiểu dữ liệu               | Null | Mặc định           | Ràng buộc             |
| ---------------- | -------------------------- | ---- | ------------------ | --------------------- |
| id               | uuid                       | No   | uuid_generate_v4() | PK                    |
| scholarship_id   | uuid                       | No   | -                  | FK -> scholarships.id |
| document_name    | varchar(255)               | No   | -                  | -                     |
| document_type    | enum(pdf,image,word,other) | No   | other              | -                     |
| is_required      | boolean                    | No   | false              | -                     |
| max_file_size_mb | integer                    | Yes  | -                  | -                     |
| sample_url       | varchar(500)               | Yes  | -                  | -                     |
| created_at       | timestamp                  | No   | now()              | -                     |
| updated_at       | timestamp                  | No   | now()              | -                     |

## 3.8.5 student_scholarships

Mục đích:

- Bảng trung tâm lưu hồ sơ đăng ký học bổng của sinh viên và kết quả xét duyệt.

| Cột DB             | Kiểu dữ liệu                                                        | Null | Mặc định           | Ràng buộc                            |
| ------------------ | ------------------------------------------------------------------- | ---- | ------------------ | ------------------------------------ |
| id                 | uuid                                                                | No   | uuid_generate_v4() | PK                                   |
| user_id            | uuid                                                                | No   | -                  | Không có FK trong migration hiện tại |
| scholarship_id     | uuid                                                                | No   | -                  | FK -> scholarships.id                |
| application_date   | timestamp                                                           | Yes  | -                  | -                                    |
| status             | enum(draft,submitted,reviewing,approved,rejected,awarded,cancelled) | No   | draft              | -                                    |
| awarded_amount     | numeric(15,2)                                                       | Yes  | -                  | -                                    |
| currency           | varchar(3)                                                          | Yes  | -                  | -                                    |
| submitted_form_url | varchar(500)                                                        | Yes  | -                  | -                                    |
| note               | text                                                                | Yes  | -                  | -                                    |
| decision_date      | timestamp                                                           | Yes  | -                  | -                                    |
| feedback           | text                                                                | Yes  | -                  | -                                    |
| reviewer_id        | uuid                                                                | Yes  | -                  | Không có FK trong migration hiện tại |
| created_at         | timestamp                                                           | No   | now()              | -                                    |
| updated_at         | timestamp                                                           | No   | now()              | -                                    |

## 3.8.6 student_scholarship_documents

Mục đích:

- Lưu file thực tế sinh viên đã nộp theo từng hồ sơ và trạng thái duyệt file.

| Cột DB                 | Kiểu dữ liệu                    | Null | Mặc định           | Ràng buộc                      |
| ---------------------- | ------------------------------- | ---- | ------------------ | ------------------------------ |
| id                     | uuid                            | No   | uuid_generate_v4() | PK                             |
| student_scholarship_id | uuid                            | No   | -                  | FK -> student_scholarships.id  |
| document_id            | uuid                            | No   | -                  | FK -> scholarship_documents.id |
| file_url               | varchar(500)                    | No   | -                  | -                              |
| upload_date            | timestamp                       | Yes  | -                  | -                              |
| status                 | enum(pending,approved,rejected) | No   | pending            | -                              |
| reviewer_note          | text                            | Yes  | -                  | -                              |
| created_at             | timestamp                       | No   | now()              | -                              |
| updated_at             | timestamp                       | No   | now()              | -                              |

## 3.8.7 scholarship_reviews

Mục đích:

- Lưu nhật ký review theo từng giai đoạn của mỗi hồ sơ.

| Cột DB                 | Kiểu dữ liệu                                                     | Null | Mặc định           | Ràng buộc                            |
| ---------------------- | ---------------------------------------------------------------- | ---- | ------------------ | ------------------------------------ |
| id                     | uuid                                                             | No   | uuid_generate_v4() | PK                                   |
| student_scholarship_id | uuid                                                             | No   | -                  | FK -> student_scholarships.id        |
| reviewer_id            | uuid                                                             | No   | -                  | Không có FK trong migration hiện tại |
| stage                  | enum(eligibility_check,document_review,interview,final_decision) | No   | eligibility_check  | -                                    |
| status                 | enum(pending,approved,rejected)                                  | No   | pending            | -                                    |
| comment                | text                                                             | Yes  | -                  | -                                    |
| reviewed_at            | timestamp                                                        | Yes  | -                  | -                                    |
| created_at             | timestamp                                                        | No   | now()              | -                                    |
| updated_at             | timestamp                                                        | No   | now()              | -                                    |

## 3.8.8 Ghi chú quan trọng về khóa ngoại

- scholarship_id có FK rõ ràng sang scholarships ở các bảng liên quan.
- category_id và provider_id của scholarships có FK tương ứng.
- reviewer_id ở student_scholarships và scholarship_reviews hiện là UUID tham chiếu mềm, chưa có FK DB-level.
- user_id ở student_scholarships hiện cũng chưa có FK DB-level trong migration đang dùng.

## 4. Luồng nghiệp vụ end-to-end

## 4.1 Luồng A - Khởi tạo một học bổng mới

### Bước A1: Tạo danh mục (nếu chưa có)

Endpoint:

- POST /scholarships/categories

Thông tin cần có:

- name
- description (tùy chọn)

Tác động dữ liệu:

- INSERT vào bảng scholarship_categories.

### Bước A2: Tạo học bổng

Endpoint:

- POST /scholarships

Thông tin tối thiểu theo DTO hiện tại:

- name

Thông tin nên có trong thực tế:

- categoryId
- providerId hoặc provider
- eligibilityCriteria
- amount, currency, quantity
- applicationDeadline
- resultAnnouncementDate
- benefits
- contact_email hoặc contactPhone
- official_website
- isActive

Tác động dữ liệu:

- INSERT vào bảng scholarships.

### Bước A3: Khai báo yêu cầu hồ sơ

Endpoint:

- POST /scholarships/:scholarship_id/requirements

Thông tin cần có:

- title
- description
- isRequired
- sortOrder

Tác động dữ liệu:

- INSERT nhiều bản ghi vào scholarship_requirements.

### Bước A4: Khai báo bộ giấy tờ cần nộp

Endpoint:

- POST /scholarships/:scholarship_id/documents

Thông tin cần có:

- documentName
- documentType
- isRequired
- maxFileSizeMb
- sampleUrl

Tác động dữ liệu:

- INSERT nhiều bản ghi vào scholarship_documents.

### Bước A5: Công bố học bổng

Endpoint:

- PUT /scholarships/:id

Thông tin thay đổi thường gặp:

- isActive = true
- deadline và thông tin hiển thị cuối cùng.

Tác động dữ liệu:

- UPDATE bảng scholarships.

## 4.2 Luồng B - Sinh viên đăng ký học bổng

Hệ thống hiện có 2 cách đăng ký.

### Cách 1: Luồng nhanh

Endpoint:

- POST /scholarships/register

Thông tin cần có:

- scholarship_id bắt buộc
- note tùy chọn

Hệ thống xử lý nội bộ:

1. Kiểm tra scholarship có tồn tại.
2. Tạo hồ sơ trong student_scholarships với status = draft.
3. Submit ngay thành status = submitted.

Tác động dữ liệu:

- INSERT vào student_scholarships.
- UPDATE chính bản ghi đó từ draft sang submitted.
- Cập nhật application_date.

### Cách 2: Luồng đầy đủ theo từng bước

#### Bước B1: Tạo hồ sơ nháp

Endpoint:

- POST /student-scholarships

Thông tin cần có:

- scholarshipId
- note (tùy chọn)

Tác động dữ liệu:

- INSERT student_scholarships với status = draft.

#### Bước B2: Upload giấy tờ theo checklist

Endpoint:

- POST /student-scholarships/:student_scholarship_id/documents

Thông tin cần có:

- documentId
- fileUrl

Tác động dữ liệu:

- INSERT vào student_scholarship_documents.
- status tài liệu mặc định = pending.

#### Bước B3: Nộp chính thức

Endpoint:

- POST /student-scholarships/:id/submit

Thông tin có thể gửi:

- submittedFormUrl
- note

Tác động dữ liệu:

- UPDATE student_scholarships:
  - status: draft -> submitted
  - application_date: thời điểm submit
  - submitted_form_url hoặc note (nếu có)

## 4.3 Luồng C - Review và ra quyết định

### C1: Duyệt tài liệu sinh viên

Endpoint:

- PUT /student-scholarships/documents/:id/status

Thông tin cần gửi:

- status: pending, approved, rejected
- reviewer_note (tùy chọn)

Tác động dữ liệu:

- UPDATE student_scholarship_documents.status
- UPDATE student_scholarship_documents.reviewer_note

### C2: Ghi nhận review theo stage

Endpoint:

- POST /student-scholarships/:student_scholarship_id/reviews

Thông tin cần gửi:

- stage: eligibility_check, document_review, interview, final_decision
- status: pending, approved, rejected
- comment
- reviewedAt

Tác động dữ liệu:

- INSERT vào scholarship_reviews.

### C3: Chốt kết quả hồ sơ

Endpoint:

- PUT /student-scholarships/:id/status

Thông tin cần gửi:

- status: reviewing, approved, rejected, awarded, ...
- feedback
- awardedAmount
- currency
- reviewerId
- decisionDate

Tác động dữ liệu:

- UPDATE student_scholarships.status
- UPDATE student_scholarships.feedback
- UPDATE student_scholarships.awarded_amount
- UPDATE student_scholarships.currency
- UPDATE student_scholarships.reviewer_id
- UPDATE student_scholarships.decision_date

Ghi chú quan trọng:

- Nếu status là approved hoặc rejected hoặc awarded mà không truyền decisionDate, service tự gán ngày hiện tại.

## 4.4 Luồng D - Sinh viên kiểm tra kết quả

Endpoint sinh viên dùng:

1. Danh sách hồ sơ của tôi

- GET /scholarships/my-scholarships
- GET /student-scholarships/my-applications

2. Chi tiết một hồ sơ

- GET /scholarships/my-scholarships/:id
- GET /student-scholarships/:id

Cách xác định đậu/rớt:

1. Đậu

- status = approved hoặc awarded

2. Rớt

- status = rejected

3. Đang xử lý

- status = submitted hoặc reviewing

Thông tin nên hiển thị cho sinh viên:

- status hiện tại
- feedback của reviewer
- decisionDate
- awardedAmount và currency (nếu có)

## 5. Trạng thái và quy tắc chuyển trạng thái

## 5.1 Trạng thái ở bảng scholarships

Bảng scholarships không dùng enum status, mà dùng cột cờ is_active.

| Trường    | Giá trị | Ý nghĩa nghiệp vụ                                 | Ai cập nhật            | Endpoint thường dùng  |
| --------- | ------- | ------------------------------------------------- | ---------------------- | --------------------- |
| is_active | true    | Học bổng đang mở hiển thị và sẵn sàng cho đăng ký | Quản trị hoặc vận hành | PUT /scholarships/:id |
| is_active | false   | Học bổng tạm ẩn hoặc ngừng nhận hồ sơ mới         | Quản trị hoặc vận hành | PUT /scholarships/:id |

Ghi chú:

- Code hiện tại chưa bắt buộc chặn đăng ký khi is_active = false trong luồng register.

## 5.2 Trạng thái ở bảng student_scholarships

Đây là trạng thái quan trọng nhất, quyết định hồ sơ đang ở giai đoạn nào và kết quả cuối cùng là gì.

| Status    | Ý nghĩa nghiệp vụ                             | Ai thường cập nhật                                | Endpoint cập nhật chính                                                | Trường thường đi kèm                                 |
| --------- | --------------------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------- |
| draft     | Hồ sơ nháp, sinh viên còn chỉnh sửa           | Hệ thống khi tạo hồ sơ hoặc sinh viên khi tạo mới | POST /student-scholarships hoặc POST /scholarships/register            | note                                                 |
| submitted | Hồ sơ đã nộp chính thức, chờ xử lý            | Sinh viên hoặc hệ thống register nhanh            | POST /student-scholarships/:id/submit hoặc POST /scholarships/register | application_date, submitted_form_url, note           |
| reviewing | Hồ sơ đang được hội đồng xử lý                | Reviewer hoặc vận hành                            | PUT /student-scholarships/:id/status                                   | feedback, reviewer_id                                |
| approved  | Hồ sơ đạt, đã qua xét duyệt                   | Reviewer hoặc vận hành                            | PUT /student-scholarships/:id/status                                   | decision_date, feedback, reviewer_id                 |
| rejected  | Hồ sơ không đạt                               | Reviewer hoặc vận hành                            | PUT /student-scholarships/:id/status                                   | decision_date, feedback, reviewer_id                 |
| awarded   | Hồ sơ được cấp học bổng (thường là bước cuối) | Reviewer hoặc vận hành                            | PUT /student-scholarships/:id/status                                   | awarded_amount, currency, decision_date, reviewer_id |
| cancelled | Sinh viên hủy hồ sơ                           | Sinh viên                                         | DELETE /scholarships/my-scholarships/:id (luồng unregister)            | status                                               |

Quy tắc chuyển trạng thái đang áp dụng trong code:

- draft -> submitted: hợp lệ qua submit.
- draft -> cancelled: hợp lệ qua unregister.
- submitted -> cancelled: hợp lệ qua unregister.
- submitted/reviewing -> approved hoặc rejected hoặc awarded: hợp lệ qua update status nghiệp vụ review.

Ràng buộc quan trọng đang enforce:

- Chỉ update nội dung hồ sơ khi status hiện tại là draft.
- Chỉ submit khi status hiện tại là draft.
- Chỉ delete cứng hồ sơ khi status hiện tại là draft.
- Chỉ cancel qua unregister khi status hiện tại thuộc draft hoặc submitted.
- Khi set status là approved, rejected, awarded mà không truyền decisionDate, service tự set decision_date = thời điểm hiện tại.

## 5.3 Trạng thái ở bảng student_scholarship_documents

Đây là trạng thái duyệt từng file mà sinh viên nộp.

| Status   | Ý nghĩa nghiệp vụ                          | Ai cập nhật          | Endpoint cập nhật                                            |
| -------- | ------------------------------------------ | -------------------- | ------------------------------------------------------------ |
| pending  | Tài liệu đã nộp, chưa được duyệt           | Hệ thống khi tạo mới | POST /student-scholarships/:student_scholarship_id/documents |
| approved | Tài liệu hợp lệ                            | Reviewer             | PUT /student-scholarships/documents/:id/status               |
| rejected | Tài liệu không hợp lệ hoặc thiếu thông tin | Reviewer             | PUT /student-scholarships/documents/:id/status               |

Trường liên quan khi duyệt:

- status
- reviewer_note

## 5.4 Trạng thái ở bảng scholarship_reviews

Bảng này có 2 trục: stage và status.

Stage thể hiện đang review ở bước nào:

- eligibility_check
- document_review
- interview
- final_decision

Status của từng bản ghi review:

| Status   | Ý nghĩa                           |
| -------- | --------------------------------- |
| pending  | Bước review đã mở nhưng chưa chốt |
| approved | Bước review này đạt               |
| rejected | Bước review này không đạt         |

Ai cập nhật:

- Reviewer tạo hoặc cập nhật review qua các endpoint reviews.

## 5.5 Mapping trạng thái để hiển thị kết quả cho sinh viên

Sinh viên nhìn trạng thái hồ sơ student_scholarships để hiểu kết quả cuối:

- approved hoặc awarded: Đậu.
- rejected: Rớt.
- submitted hoặc reviewing: Đang xử lý.
- cancelled: Đã hủy đăng ký.
- draft: Chưa nộp chính thức.

## 6. Ma trận tác động dữ liệu theo thao tác

1. Tạo học bổng

- Bảng: scholarships
- Thao tác: INSERT
- Trường cốt lõi: name, category_id, provider_id, amount, deadline, is_active

2. Tạo yêu cầu

- Bảng: scholarship_requirements
- Thao tác: INSERT
- Trường cốt lõi: scholarship_id, title, is_required, sort_order

3. Tạo loại giấy tờ

- Bảng: scholarship_documents
- Thao tác: INSERT
- Trường cốt lõi: scholarship_id, document_name, document_type, is_required

4. Sinh viên tạo hồ sơ

- Bảng: student_scholarships
- Thao tác: INSERT
- Trường cốt lõi: user_id, scholarship_id, status=draft, note

5. Sinh viên submit hồ sơ

- Bảng: student_scholarships
- Thao tác: UPDATE
- Trường đổi: status=submitted, application_date, submitted_form_url, note

6. Sinh viên upload file

- Bảng: student_scholarship_documents
- Thao tác: INSERT
- Trường cốt lõi: student_scholarship_id, document_id, file_url, status=pending

7. Reviewer duyệt tài liệu

- Bảng: student_scholarship_documents
- Thao tác: UPDATE
- Trường đổi: status, reviewer_note

8. Reviewer ghi log review

- Bảng: scholarship_reviews
- Thao tác: INSERT
- Trường cốt lõi: student_scholarship_id, reviewer_id, stage, status, comment

9. Reviewer chốt kết quả hồ sơ

- Bảng: student_scholarships
- Thao tác: UPDATE
- Trường đổi: status, feedback, reviewer_id, decision_date, awarded_amount, currency

## 7. Danh sách endpoint đầy đủ

## 7.1 Categories

- GET /scholarships/categories
- GET /scholarships/categories/:id
- POST /scholarships/categories
- PUT /scholarships/categories/:id
- DELETE /scholarships/categories/:id

## 7.2 Scholarships

- GET /scholarships
- GET /scholarships/organization/:organization_id
- GET /scholarships/:id
- POST /scholarships
- PUT /scholarships/:id
- DELETE /scholarships/:id

Filter cho GET /scholarships:

- category_id
- provider_id
- provider
- active
- open_application
- high_amount
- search
- page
- limit

## 7.3 Scholarship Requirements

- GET /scholarships/:scholarship_id/requirements
- GET /scholarships/requirements/:id
- POST /scholarships/:scholarship_id/requirements
- PUT /scholarships/requirements/:id
- DELETE /scholarships/requirements/:id

## 7.4 Scholarship Documents

- GET /scholarships/:scholarship_id/documents
- GET /scholarships/documents/:id
- POST /scholarships/:scholarship_id/documents
- PUT /scholarships/documents/:id
- DELETE /scholarships/documents/:id

## 7.5 Student Scholarships

- GET /student-scholarships
- GET /student-scholarships/my-applications
- GET /student-scholarships/:id
- POST /student-scholarships
- PUT /student-scholarships/:id
- POST /student-scholarships/:id/submit
- PUT /student-scholarships/:id/status
- DELETE /student-scholarships/:id

## 7.6 Quick Flow cho user

- POST /scholarships/register
- GET /scholarships/my-scholarships
- GET /scholarships/my-scholarships/:id
- DELETE /scholarships/my-scholarships/:id

## 7.7 Student Scholarship Documents

- GET /student-scholarships/:student_scholarship_id/documents
- GET /student-scholarships/documents/:id
- POST /student-scholarships/:student_scholarship_id/documents
- PUT /student-scholarships/documents/:id/status
- DELETE /student-scholarships/documents/:id

## 7.8 Reviews

- GET /student-scholarships/:student_scholarship_id/reviews
- GET /student-scholarships/reviews/:id
- POST /student-scholarships/:student_scholarship_id/reviews
- PUT /student-scholarships/reviews/:id
- DELETE /student-scholarships/reviews/:id

## 8. Ví dụ payload nhanh theo từng khâu

## 8.1 Tạo học bổng

```json
{
  "name": "FPT University Merit Scholarship 2026",
  "description": "Học bổng cho sinh viên thành tích cao",
  "eligibilityCriteria": "GPA >= 3.5",
  "categoryId": "550e8400-e29b-41d4-a716-446655440001",
  "providerId": "550e8400-e29b-41d4-a716-446655440010",
  "amount": 10000000,
  "currency": "VND",
  "quantity": 50,
  "applicationDeadline": "2026-05-31T23:59:59Z",
  "resultAnnouncementDate": "2026-06-20T00:00:00Z",
  "benefits": "Miễn giảm học phí",
  "isActive": true
}
```

## 8.2 Sinh viên tạo hồ sơ

```json
{
  "scholarshipId": "550e8400-e29b-41d4-a716-446655440111",
  "note": "Em có GPA 3.8 và hoạt động nghiên cứu tốt"
}
```

## 8.3 Sinh viên upload giấy tờ

```json
{
  "documentId": "550e8400-e29b-41d4-a716-446655440222",
  "fileUrl": "https://storage.example.com/docs/transcript-2026.pdf"
}
```

## 8.4 Reviewer chốt trạng thái hồ sơ

```json
{
  "status": "awarded",
  "feedback": "Hồ sơ đạt yêu cầu, đề xuất cấp học bổng",
  "awardedAmount": 10000000,
  "currency": "VND",
  "reviewerId": "550e8400-e29b-41d4-a716-446655440999"
}
```

## 9. Lưu ý triển khai theo hiện trạng code

1. Auth guard hiện chưa đồng nhất giữa các controller

- StudentScholarships và Reviews đã bật class-level guard.
- Một số controller khác đang comment guard, cần xác nhận chính sách bảo mật trước khi production.

2. Rule nghiệp vụ đăng ký hiện mới kiểm tra tồn tại học bổng

- Luồng register chưa chặn rõ ràng theo is_active hoặc application_deadline.
- Nếu muốn chặt hơn, cần bổ sung điều kiện ở service trước khi tạo hồ sơ.

3. Đồng nhất naming trường giữa API và entity

- Có chỗ dùng snake_case ở DTO, có chỗ dùng camelCase.
- Cần thống nhất để tránh mapping sai khi mở rộng API.

4. Kiểm tra nhất quán user id trong endpoint xóa hồ sơ

- Các endpoint khác thường dùng user.userId.
- Endpoint delete trong student-scholarships controller đang truyền user.id, cần kiểm tra object CurrentUser thực tế để tránh sai lệch.

## 10. Kết luận ngắn

Luồng chuẩn nên vận hành theo thứ tự:

1. Quản trị tạo học bổng và định nghĩa checklist hồ sơ.
2. Sinh viên tạo hồ sơ, nộp tài liệu, submit.
3. Reviewer duyệt tài liệu, ghi nhận review từng stage, chốt status hồ sơ.
4. Sinh viên tra cứu ở màn hình hồ sơ của tôi để biết kết quả đậu/rớt qua trường status, feedback, decisionDate và awardedAmount.
