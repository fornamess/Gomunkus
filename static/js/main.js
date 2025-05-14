// Функция для обновления статистики пользователя
function updateUserStats(stats) {
    // Обновляем баланс
    $('#user-balance span').text(stats.balance.toFixed(2));
    $('#stat-balance').text(stats.balance.toFixed(2));
    
    // Обновляем уровень
    $('#user-level span').text(stats.level);
    $('#stat-level').text(stats.level);
    
    // Обновляем опыт
    $('#stat-experience').text(`Опыт: ${stats.experience}/${stats.next_level}`);
    
    // Обновляем прогресс-бары
    let progress = (stats.experience % 100) / 100 * 100;
    $('#experience-bar, #stat-experience-bar').css('width', progress + '%');
    
    // Обновляем общую помощь
    $('#stat-total-help').text(stats.total_help.toFixed(2));
    
    // Обновляем количество завершенных проектов
    $('#stat-projects').text(stats.completed_projects);
    
    // Проверяем достижения
    checkAchievements(stats);
}

// Функция для проверки достижений
function checkAchievements(stats) {
    const achievements = [
        { id: 'level-1', condition: stats.level >= 1, text: 'Первый уровень' },
        { id: 'help-100', condition: stats.total_help >= 100, text: '100 единиц помощи' },
        { id: 'project-1', condition: stats.completed_projects >= 1, text: 'Первый завершенный проект' },
        { id: 'exp-1000', condition: stats.experience >= 1000, text: '1000 опыта' }
    ];
    
    achievements.forEach(achievement => {
        const element = $(`.achievement[data-id="${achievement.id}"]`);
        if (achievement.condition) {
            element.addClass('achieved');
            element.find('i').addClass('text-warning');
        }
    });
}

// Функция для обновления проектов
function updateProjects(projects) {
    projects.forEach(project => {
        const progress = (project.current_amount / project.target_amount * 100).toFixed(0);
        $(`#project-${project.id} .progress-bar`).css('width', `${progress}%`);
        $(`#project-${project.id} .progress-bar`).text(`${progress}%`);
        $(`#project-${project.id} .current-amount`).text(project.current_amount.toFixed(2));
    });
}

// Функция для помощи проекту
function helpProject(projectId, amount) {
    $.ajax({
        url: `/help_project/${projectId}`,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ amount: amount }),
        success: function(response) {
            if (response.success) {
                // Обновляем баланс
                $('#user-balance span').text(response.new_balance.toFixed(2));
                $('#stat-balance').text(response.new_balance.toFixed(2));
                
                // Обновляем прогресс проекта
                $(`#project-${projectId} .progress-bar`).css('width', response.project_progress + '%');
                $(`#project-${projectId} .progress-bar`).text(response.project_progress + '%');
                
                // Показываем уведомление
                showNotification('Спасибо за помощь!', 'success');
            }
        },
        error: function(xhr) {
            showNotification(xhr.responseJSON.error, 'error');
        }
    });
}

// Функция для показа уведомлений
function showNotification(message, type = 'info') {
    const alert = $(`
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `);
    
    $('.container').prepend(alert);
    
    setTimeout(() => {
        alert.alert('close');
    }, 5000);
}

// Инициализация при загрузке страницы
$(document).ready(function() {
    // Загружаем начальную статистику
    $.get('/user_stats', function(stats) {
        updateUserStats(stats);
    });
    
    // Загружаем проекты
    $.get('/projects', function(projects) {
        updateProjects(projects);
    });
    
    // Обработчик для кнопок помощи
    $('.help-btn').click(function() {
        const projectId = $(this).data('project-id');
        const amount = $(this).data('amount');
        
        if (confirm(`Вы уверены, что хотите помочь проекту на сумму ${amount}?`)) {
            $.post(`/help_project/${projectId}`, { amount: amount }, function(response) {
                if (response.error) {
                    showNotification(response.error, 'error');
                    return;
                }
                
                showNotification(`Спасибо за помощь! Вы пожертвовали ${amount}`, 'success');
                setTimeout(() => location.reload(), 1500);
            });
        }
    });
    
    // Анимация для карточек
    $('.card').each(function(index) {
        $(this).css('animation-delay', `${index * 0.1}s`);
    });
    
    // Анимация для прогресс-баров
    $('.progress-bar').each(function() {
        const width = $(this).css('width');
        $(this).css('width', '0');
        setTimeout(() => {
            $(this).css('width', width);
        }, 100);
    });
    
    // Обработчик для кнопки тапа
    let cooldown = false;
    $('#tap-button').click(function() {
        if (cooldown) return;
        
        cooldown = true;
        $(this).addClass('active');
        
        $.post('/tap', function(response) {
            if (response.error) {
                showNotification(response.error, 'error');
                return;
            }
            
            updateUserStats(response);
            showRewardAnimation(response.reward);
            
            setTimeout(function() {
                cooldown = false;
                $('#tap-button').removeClass('active');
            }, 1000);
        });
    });
});

// Функция для анимации награды
function showRewardAnimation(reward) {
    const animation = $('<div>')
        .addClass('reward-animation')
        .text('+' + reward.toFixed(2))
        .appendTo('.tap-area');
        
    setTimeout(function() {
        animation.remove();
    }, 1000);
} 