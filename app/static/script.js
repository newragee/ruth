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

// --- Универсальная функция для вызовов API ---
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
                errorDetail = errorData.detail || JSON.stringify(errorData);
            } catch (e) {
                try {
                    errorDetail = await response.text();
                } catch (textError) {}
            }
            throw new Error(errorDetail);
        }

        return await response.json();
    } catch (error) {
        if (error instanceof Error) {
            throw error;
        }
        throw new Error(String(error));
    }
}

// --- Обработчики после загрузки DOM ---
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
                alert('Ошибка регистрации: ' + (err.message || String(err)));
            }
        });
    }

    // Логика главной страницы
    const authSection = document.getElementById('auth-section');
    const mainMenu = document.getElementById('main-menu');
    if (authSection && mainMenu) {
        const token = getToken();
        if (token) {
            authSection.innerHTML = '<p>Вы авторизованы. <a href="#" id="logout">Выйти</a></p>';
            mainMenu.style.display = 'block';
            document.getElementById('logout').addEventListener('click', (e) => {
                e.preventDefault();
                removeToken();
                window.location.reload();
            });
        } else {
            authSection.innerHTML = '<p><a href="/login">Войти</a> | <a href="/register">Зарегистрироваться</a></p>';
            mainMenu.style.display = 'none';
        }
    }
});
