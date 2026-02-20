// ================== script.js ==================

// --- Управление токеном ---
function setToken(token) {
    localStorage.setItem('token', token);
}

function getToken() {
    return localStorage.getItem('token');
}

function removeToken() {
    localStorage.removeItem('token');
}

// --- Универсальная функция для вызовов API с улучшенной обработкой ошибок ---
async function apiCall(url, method, body, token) {
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    try {
        const response = await fetch(url, {
            method,
            headers,
            body: body ? JSON.stringify(body) : undefined
        });

        if (!response.ok) {
            let errorDetail = `HTTP error ${response.status}`;
            try {
                const errorData = await response.json();
                // Если сервер вернул JSON с полем detail, используем его
                errorDetail = errorData.detail || JSON.stringify(errorData);
            } catch (e) {
                // Если JSON не парсится, пробуем получить текст
                try {
                    errorDetail = await response.text();
                } catch (textError) {
                    // Если и текст не получить, оставляем статус
                }
            }
            throw new Error(errorDetail);
        }

        return await response.json();
    } catch (error) {
        // Гарантируем, что всегда выбрасывается Error с сообщением
        if (error instanceof Error) {
            throw error;
        } else {
            throw new Error(String(error));
        }
    }
}

// --- Обработчики событий после загрузки DOM ---
document.addEventListener('DOMContentLoaded', () => {
    
    // Форма входа
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            try {
                const data = await apiCall('/api/v1/auth/login', 'POST', { username, password });
                setToken(data.access_token);
                window.location.href = '/';
            } catch (err) {
                console.error('Login error:', err);
                alert('Ошибка входа: ' + (err.message || String(err)));
            }
        });
    }

    // Форма регистрации
    const registerForm = document.getElementById('register-form');
    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            try {
                const data = await apiCall('/api/v1/auth/register', 'POST', { username, password });
                setToken(data.access_token);
                window.location.href = '/';
            } catch (err) {
                console.error('Registration error:', err);
                alert('Ошибка регистрации: ' + (err.message || String(err)));
            }
        });
    }

    // Форма чата
    const chatForm = document.getElementById('chat-form');
    if (chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const message = document.getElementById('message').value;
            const token = getToken();
            if (!token) {
                alert('Необходимо авторизоваться');
                window.location.href = '/';
                return;
            }
            try {
                const data = await apiCall('/api/v1/chat/', 'POST', { message }, token);
                const responseDiv = document.getElementById('response');
                if (responseDiv) {
                    responseDiv.innerHTML = `<p><strong>Ответ:</strong> ${data.response}</p>`;
                    if (data.extracted_metrics && data.extracted_metrics.length) {
                        responseDiv.innerHTML += `<p><em>Сохранены показатели: ${data.extracted_metrics.join(', ')}</em></p>`;
                    }
                }
            } catch (err) {
                console.error('Chat error:', err);
                alert('Ошибка чата: ' + (err.message || String(err)));
            }
        });
    }

    // --- Логика главной страницы (индекса) ---
    const authSection = document.getElementById('auth-section');
    const mainMenu = document.getElementById('main-menu');
    if (authSection && mainMenu) {
        const token = getToken();
        if (token) {
            authSection.innerHTML = '<p>Вы авторизованы. <a href="#" id="logout">Выйти</a></p>';
            mainMenu.style.display = 'block';
            const logoutBtn = document.getElementById('logout');
            if (logoutBtn) {
                logoutBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    removeToken();
                    window.location.reload();
                });
            }
        } else {
            authSection.innerHTML = '<p><a href="/login">Войти</a> | <a href="/register">Зарегистрироваться</a></p>';
            mainMenu.style.display = 'none';
        }
    }
});